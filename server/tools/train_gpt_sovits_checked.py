"""Run an isolated GPT-SoVITS v2ProPlus quick trial with checked stage gates.

Use the GPT-SoVITS bundled Python. Never reuse an existing experiment directory.
The input manifest must already be reviewed; automated checks do not replace listening.
"""
import argparse
import ast
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
import traceback
import wave

import yaml


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_features(root, out):
    # Run in a child process so torch/text libraries are released before training.
    sys.path.insert(0, str(root/'GPT_SoVITS'))
    sys.path.insert(0, str(root))
    from text.cleaner import clean_text
    import torch
    rows = [line.split('|') for line in (out/'training_input.list').read_text(encoding='utf-8').splitlines()]
    texts = {r[0]:r for r in (line.split('\t') for line in (out/'2-name2text.txt').read_text(encoding='utf-8').splitlines())}
    for row in rows:
        audio_name = Path(row[0]).name
        phones, word2ph, normalized = clean_text(row[3].replace('%','-').replace('￥',','), 'zh', 'v2ProPlus')
        actual = texts[audio_name]
        assert len(actual) == 4 and actual[3] == normalized, audio_name
        assert actual[1] == ' '.join(phones) and ast.literal_eval(actual[2]) == word2ph
        bert = torch.load(out/'3-bert'/(audio_name+'.pt'), map_location='cpu', weights_only=False)
        assert bert.shape[-1] == len(phones)
    print('Validated 39 text/phoneme/BERT mappings', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--resume-validated', action='store_true', help='Retry failed pre-checkpoint training with the same frozen input')
    parser.add_argument('--validate-features', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    root, manifest = args.root.resolve(), args.manifest.resolve()
    name = args.experiment
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in name):
        raise ValueError('Use a simple experiment name')
    out = root / 'logs' / name
    if args.validate_features:
        validate_features(root, out)
        return
    if args.resume_validated:
        previous = json.loads((out/'pipeline_status.json').read_text(encoding='utf-8'))
        assert previous['stage'] == 'failed'
        assert previous['manifest_sha256'] == digest(manifest) == digest(out/'training_input.list')
        assert not list(out.glob('logs_s2_*/*.pth')), 'Checkpoint exists; explicit continuation review required'
        assert not list(out.glob('logs_s1_*/ckpt/*.ckpt'))
        archive = out / ('attempt_before_retry_' + time.strftime('%Y%m%d_%H%M%S'))
        archive.mkdir(exist_ok=False)
        for file in out.iterdir():
            if file.is_file() and file.suffix in {'.log','.json','.yaml'}:
                shutil.copy2(file, archive/file.name)
    else:
        out.mkdir(exist_ok=False)
    os.chdir(root)
    started = time.time()
    state = {'experiment': name, 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'stages': []}

    def status(stage, detail=''):
        state.update(stage=stage, detail=detail, elapsed_s=round(time.time()-started, 2))
        (out / 'pipeline_status.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[{time.strftime("%H:%M:%S")}] {stage}: {detail}', flush=True)

    try:
        for directory, extension in [('GPT_weights_v2ProPlus', '.ckpt'), ('SoVITS_weights_v2ProPlus', '.pth')]:
            if list((root / directory).glob(name + '*' + extension)):
                raise ValueError('Export weights already exist; choose a new experiment')
        rows = [line.split('|') for line in manifest.read_text(encoding='utf-8').splitlines() if line.strip()]
        assert len(rows) == 39 and all(len(r) == 4 and r[2] == 'ZH' and r[3].strip() for r in rows)
        names = [Path(r[0]).name for r in rows]
        assert len(set(names)) == len(names)
        audio_audit = []
        for i, row in enumerate(rows):
            audio_path = Path(row[0])
            with wave.open(str(audio_path), 'rb') as wav:
                duration = wav.getnframes() / wav.getframerate()
                assert 2 <= duration <= 12 and wav.getnchannels() == 1
            audio_audit.append({'index': i, 'audio': str(audio_path), 'seconds': duration,
                                'sha256': digest(audio_path), 'text': row[3]})
        assert rows[0][3].startswith('曼波视频傻瓜式剪辑教程')
        assert rows[10][3].startswith('然后,点击开始创作')
        assert all(rows[i][3] != rows[i+10][3] for i in range(10))
        frozen = out / 'training_input.list'
        frozen.write_bytes(manifest.read_bytes())
        frozen_hash = digest(frozen)
        (out / 'input_audit.json').write_text(json.dumps(audio_audit, ensure_ascii=False, indent=2), encoding='utf-8')
        state['manifest_sha256'] = frozen_hash
        env = os.environ.copy()
        env.update(version='v2ProPlus', inp_text=str(frozen), inp_wav_dir=str(Path(rows[0][0]).parent),
                   exp_name=name, opt_dir=str(out), i_part='0', all_parts='1', _CUDA_VISIBLE_DEVICES='0',
                   CUDA_VISIBLE_DEVICES='0', is_half='True', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
                   bert_pretrained_dir=str(root/'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'),
                   cnhubert_base_dir=str(root/'GPT_SoVITS/pretrained_models/chinese-hubert-base'),
                   sv_path=str(root/'GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt'),
                   pretrained_s2G=str(root/'GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth'),
                   s2config_path=str(root/'GPT_SoVITS/configs/s2v2ProPlus.json'))
        env['PATH'] = str(root/'runtime') + os.pathsep + env.get('PATH', '')
        env['PYTHONPATH'] = str(root) + os.pathsep + str(root/'GPT_SoVITS')
        env['PRP_TRAIN_NUM_WORKERS'] = '0'

        def run(stage, command):
            assert digest(frozen) == frozen_hash, 'Frozen training manifest changed'
            status(stage, 'running')
            begin = time.time()
            with (out/(stage+'.out.log')).open('w', encoding='utf-8') as stdout, (out/(stage+'.err.log')).open('w', encoding='utf-8') as stderr:
                result = subprocess.run([sys.executable, '-s'] + command, cwd=root, env=env,
                                        stdout=stdout, stderr=stderr, check=False)
            state['stages'].append({'name':stage, 'seconds':round(time.time()-begin, 2), 'returncode':result.returncode})
            if result.returncode:
                raise RuntimeError(f'{stage} failed with exit {result.returncode}; see stage logs')
            status(stage, 'process exited successfully; checking outputs')

        for stage, script in [('01_text','1-get-text.py'), ('02_hubert','2-get-hubert-wav32k.py'),
                              ('03_speaker','2-get-sv.py'), ('04_semantic','3-get-semantic.py')]:
            run(stage, ['GPT_SoVITS/prepare_datasets/'+script])
        text_part = out/'2-name2text-0.txt'
        semantic_part = out/'6-name2semantic-0.tsv'
        (out/'2-name2text.txt').write_bytes(text_part.read_bytes())
        (out/'6-name2semantic.tsv').write_text('item_name\tsemantic_audio\n'+semantic_part.read_text(encoding='utf-8'), encoding='utf-8')
        expected = set(names)
        for directory, suffix in [('3-bert','.pt'), ('4-cnhubert','.pt'), ('5-wav32k',''), ('7-sv_cn','.pt')]:
            files = list((out/directory).iterdir())
            assert {p.name[:-len(suffix)] if suffix else p.name for p in files} == expected, directory
            assert all(p.stat().st_size > 0 for p in files), directory
        texts = {r[0]:r for r in (line.split('\t') for line in text_part.read_text(encoding='utf-8').splitlines())}
        semantics = {r[0]:r[1] for r in (line.split('\t') for line in semantic_part.read_text(encoding='utf-8').splitlines())}
        assert set(texts) == set(semantics) == expected
        # Recompute normalization from the frozen manifest, checking every audio/text pairing.
        assert all(semantics[n].strip() for n in names)
        run('04b_validate', [str(Path(__file__).resolve()), '--root',str(root), '--manifest',str(manifest),
                             '--experiment',name, '--validate-features'])
        status('feature_validation', '39 audio/text pairs, normalization and BERT lengths verified')
        s2 = json.loads((root/'GPT_SoVITS/configs/s2v2ProPlus.json').read_text())
        s2['train'].update(batch_size=4, epochs=4, text_low_lr_rate=0.4, if_save_latest=True,
                           if_save_every_weights=True, save_every_epoch=2, gpu_numbers='0',
                           pretrained_s2G=env['pretrained_s2G'],
                           pretrained_s2D=str(root/'GPT_SoVITS/pretrained_models/v2Pro/s2Dv2ProPlus.pth'))
        s2['model']['version']='v2ProPlus'
        s2['data']['exp_dir']=str(out)
        s2.update(s2_ckpt_dir=str(out), save_weight_dir=str(root/'SoVITS_weights_v2ProPlus'), name=name, version='v2ProPlus')
        s2path=out/'run_s2.json'
        s2path.write_text(json.dumps(s2, indent=2), encoding='utf-8')
        (out/'logs_s2_v2ProPlus').mkdir(exist_ok=True)
        run('05_sovits', ['GPT_SoVITS/s2_train.py','--config',str(s2path)])
        sovits=list((root/'SoVITS_weights_v2ProPlus').glob(name+'_e4_s*.pth'))
        assert len(sovits)==1 and '====> Epoch: 4' in (out/'train.log').read_text(encoding='utf-8')
        s1=yaml.safe_load((root/'GPT_SoVITS/configs/s1longer-v2.yaml').read_text())
        s1['data']['num_workers'] = 1
        s1['train'].update(batch_size=4, epochs=5, save_every_n_epoch=5, if_save_every_weights=True,
                           if_save_latest=True, if_dpo=False, half_weights_save_dir=str(root/'GPT_weights_v2ProPlus'), exp_name=name)
        s1.update(pretrained_s1=str(root/'GPT_SoVITS/pretrained_models/s1v3.ckpt'),
                  train_semantic_path=str(out/'6-name2semantic.tsv'), train_phoneme_path=str(out/'2-name2text.txt'),
                  output_dir=str(out/'logs_s1_v2ProPlus'))
        s1path=out/'run_s1.yaml'
        s1path.write_text(yaml.safe_dump(s1), encoding='utf-8')
        env['hz']='25hz'
        run('06_gpt', ['GPT_SoVITS/s1_train.py','--config_file',str(s1path)])
        gpt=root/'GPT_weights_v2ProPlus'/(name+'-e5.ckpt')
        assert gpt.exists()
        assert 'max_epochs=5' in (out/'06_gpt.err.log').read_text(encoding='utf-8')
        sys.path.insert(0, str(root/'GPT_SoVITS'))
        import torch
        from process_ckpt import load_sovits_new
        for p in [gpt,sovits[0]]:
            assert p.stat().st_size>1000000
            obj=(load_sovits_new(str(p)) if p.suffix == '.pth'
                 else torch.load(p, map_location='cpu', weights_only=False))
            assert isinstance(obj,dict) and obj.get('weight')
            del obj
        state['weights']={'gpt':str(gpt),'sovits':str(sovits[0])}
        assert digest(frozen)==frozen_hash
        status('training_complete', 'both weight files validated; inference listening still required')
    except BaseException as error:
        status('failed', str(error))
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main()
