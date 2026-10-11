#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <algorithm>
#include <atomic>
#include <thread>
#include <vector>
#include "../../main/audio_volume.h"
#include "../../main/audio_volume_protocol.h"
#include "../../main/audio_playback_gate.h"

static std::vector<uint8_t> render(const uint8_t *data, size_t length, int percent,
                                 size_t max_write = 480) {
    std::vector<uint8_t> output;
    const esp_err_t ret = pcm16_write_attenuated(data, length, [=]() { return percent; },
        [&](const uint8_t *p, size_t n, size_t *written) {
            *written = std::min(n, max_write);
            output.insert(output.end(), p, p + *written);
            return ESP_OK;
        });
    assert(ret == ESP_OK);
    return output;
}

int main() {
    AudioVolume state;
    assert(state.get() == 100);
    for (int value : {0, 50, 100}) { assert(state.set(value)); assert(state.get() == value); }
    for (int value : {-2147483647, -1, 101, 2147483647}) {
        assert(!state.set(value)); assert(state.get() == 100);
    }
    // Every PCM16 value, unaligned input, exact 100%, silence and attenuation.
    std::vector<uint8_t> source(1 + 65536 * 2, 0xA5);
    for (unsigned raw = 0; raw < 65536; ++raw) {
        source[1 + 2 * raw] = uint8_t(raw);
        source[2 + 2 * raw] = uint8_t(raw >> 8);
    }
    const auto original = source;
    for (int percent : {0, 1, 50, 99, 100}) {
        auto output = render(source.data() + 1, source.size() - 1, percent, 7);
        assert(output.size() == source.size() - 1 && source == original);
        for (int raw = 0; raw < 65536; ++raw) {
            const int sample = raw >= 32768 ? raw - 65536 : raw;
            const int encoded = output[2 * raw] | (int(output[2 * raw + 1]) << 8);
            const int actual = encoded >= 32768 ? encoded - 65536 : encoded;
            assert(actual == sample * percent / 100);
            assert(actual >= -32768 && actual <= 32767);
        }
    }
    static const uint8_t readonly[] = {0, 128, 255, 127, 1, 0, 255, 255};
    assert((render(readonly, sizeof(readonly), 50) == std::vector<uint8_t>{0,192,255,63,0,0,0,0}));
    int writes = 0;
    auto writer = [&](const uint8_t *, size_t n, size_t *written) { ++writes; *written=n; return ESP_OK; };
    auto full = []() { return 100; };
    assert(pcm16_write_attenuated(nullptr, 2, full, writer) == ESP_ERR_INVALID_ARG);
    assert(pcm16_write_attenuated(readonly, 0, full, writer) == ESP_ERR_INVALID_ARG);
    assert(pcm16_write_attenuated(readonly, 3, full, writer) == ESP_ERR_INVALID_ARG);
    assert(pcm16_write_attenuated(readonly, 8, [](){return 101;}, writer) == ESP_ERR_INVALID_ARG);
    assert(writes == 0);
    for (int failure : {0, 1, 2}) {
        writes = 0;
        const esp_err_t ret = pcm16_write_attenuated(readonly, 8, full,
            [&](const uint8_t *, size_t n, size_t *written) {
                ++writes; *written = failure == 0 ? 0 : (failure == 1 ? n + 1 : 3);
                return failure == 2 ? ESP_ERR_TIMEOUT : ESP_OK;
            });
        assert(ret == (failure == 2 ? ESP_ERR_TIMEOUT : ESP_FAIL));
        assert(writes == 1); // zero progress, over-report or failed prefix never loops/replays
    }
    // A setting changed during a partial write affects only the next block.
    state.set(100);
    std::vector<uint8_t> blocks(482, 0);
    for (size_t i=0; i<blocks.size(); i+=2) blocks[i+1]=64;
    std::vector<uint8_t> output;
    writes=0;
    assert(pcm16_write_attenuated(blocks.data(), blocks.size(), [&](){return state.get();},
        [&](const uint8_t *p, size_t n, size_t *written) {
            ++writes; *written = std::min<size_t>(n, 31);
            output.insert(output.end(), p, p+*written);
            state.set(0);
            return ESP_OK;
        }) == ESP_OK);
    assert(std::equal(output.begin(), output.begin()+480, blocks.begin()));
    assert(output[480] == 0 && output[481] == 0 && writes > 2);

    // Real atomic state can be read concurrently without out-of-range/torn values.
    std::thread setter([&](){for(int i=0;i<100000;++i) assert(state.set(i%101));});
    for(int i=0;i<100000;++i) { int p=state.get(); assert(p>=0 && p<=100); }
    setter.join();

    for (const char *text : {"volume set a 0", "volume set a 50", "volume set a 100", "volume set a 050"}) {
        auto command=parse_audio_volume_command(text);
        assert(!command.error && command.set && !strcmp(command.id,"a"));
    }
    auto query=parse_audio_volume_command("volume get ui_001");
    assert(!query.error && !query.set && !strcmp(query.id,"ui_001"));
    for (const char *text : {"volume set a -1", "volume set a 101", "volume set a +1",
            "volume set a 50.0", "volume set a 50%", "volume set a 999999999999999999999",
            "volume set a nan", "volume set a", "volume set a 5 trailing", "volume get a 5",
            "volume get", "volume", "volume bogus a", "volume get x\"y", "volume get a/b",
            "volume get aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "volumeget a"}) {
        assert(parse_audio_volume_command(text).error);
    }
    assert(parse_audio_volume_command(nullptr).error);

    // Muting does not suppress start callback; same gate rejects reentrancy.
    int starts=0, prepare=0;
    auto callback=[](void *context) {
        ++*static_cast<int *>(context);
        AudioPlaybackGuard nested;
        assert(!nested.acquired());
    };
    for(int percent : {0, 50, 100}) {
        assert(audio_playback_run([&](){++prepare; return ESP_OK;}, [&](){
            assert(prepare == starts);
            assert(render(readonly, 8, percent, 1).size() == 8);
            return ESP_OK;
        },callback,&starts) == ESP_OK);
    }
    assert(starts==3);
    assert(audio_playback_run([](){return ESP_FAIL;}, [](){assert(false);return ESP_OK;}, callback,&starts)==ESP_FAIL);
    assert(starts==3);
    { AudioPlaybackGuard busy;
      assert(audio_playback_run([](){assert(false);return ESP_OK;}, [](){assert(false);return ESP_OK;},callback,&starts)==ESP_ERR_INVALID_STATE); }
    assert(audio_playback_run([](){return ESP_OK;}, [](){return ESP_ERR_TIMEOUT;},callback,&starts)==ESP_ERR_TIMEOUT);
    assert(starts==4);
    puts("PASS: volume PCM16/protocol/atomic/chunk/partial/error/start-gate software checks; no hardware.");
}
