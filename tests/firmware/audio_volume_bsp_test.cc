#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <algorithm>
#include <string>
#include <vector>
#include "../../main/bsp_board.cc" // Real BSP with simulated SDK; no hardware I/O.

static std::vector<std::string> events;
static std::vector<uint8_t> output;
static bool fail_enable=false, fail_write=false;
static int callbacks=0;

esp_err_t i2s_new_channel(const i2s_chan_config_t *cfg, i2s_chan_handle_t *tx, i2s_chan_handle_t *rx) {
    if(tx) {
        assert(cfg->dma_desc_num==6 && cfg->dma_frame_num==240 && cfg->auto_clear_after_cb);
        *tx=reinterpret_cast<void *>(1);
    }
    if(rx) *rx=reinterpret_cast<void *>(2);
    events.push_back("new"); return ESP_OK;
}
esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t, const i2s_std_config_t *) {return ESP_OK;}
esp_err_t i2s_channel_enable(i2s_chan_handle_t) {events.push_back("enable");return fail_enable?ESP_FAIL:ESP_OK;}
esp_err_t i2s_channel_disable(i2s_chan_handle_t) {events.push_back("disable");return ESP_OK;}
esp_err_t i2s_channel_write(i2s_chan_handle_t, const void *data, size_t length, size_t *written, uint32_t) {
    events.push_back("write");
    *written=std::min<size_t>(length,7); // odd partial writes exercise exact byte continuation
    auto p=static_cast<const uint8_t *>(data); output.insert(output.end(),p,p+*written);
    return fail_write?ESP_ERR_TIMEOUT:ESP_OK;
}
esp_err_t i2s_channel_read(i2s_chan_handle_t, void *data, size_t length, size_t *read, uint32_t) {
    memset(data,0x55,length);*read=length;return ESP_OK;
}
void vTaskDelay(uint32_t ticks) {
    events.push_back("delay"+std::to_string(ticks));
    // Ownership must still cover warm-up and DMA drain.
    AudioPlaybackGuard nested; assert(!nested.acquired());
}
static void started(void *) {
    ++callbacks; events.push_back("start");
    assert(bsp_audio_stop()==ESP_ERR_INVALID_STATE);
}
int main() {
    static const uint8_t pcm[]={0,128,255,127,0,64,0,192};
    assert(!bsp_audio_volume_ready() && bsp_audio_get_volume()==100);
    assert(bsp_audio_set_volume(50)==ESP_ERR_INVALID_STATE);
    assert(bsp_audio_set_volume(-1)==ESP_ERR_INVALID_ARG);
    assert(bsp_play_audio_with_start(pcm,8,started,nullptr)==ESP_ERR_INVALID_STATE);
    assert(callbacks==0);
    assert(bsp_audio_init(16000,1,32)==ESP_ERR_INVALID_ARG && events.empty());
    assert(bsp_audio_init(0,1,16)==ESP_ERR_INVALID_ARG);
    assert(bsp_audio_init(16000,3,16)==ESP_ERR_INVALID_ARG);
    assert(bsp_audio_init(16000,1,16)==ESP_OK);
    assert((events==std::vector<std::string>{"new","enable","delay20"}));
    assert(bsp_audio_volume_ready());
    assert(bsp_audio_init(16000,1,16)==ESP_ERR_INVALID_STATE);
    for(int percent : {0,50,100}) {
        events.clear();output.clear();
        assert(bsp_audio_set_volume(percent)==ESP_OK);
        assert(bsp_audio_set_volume(101)==ESP_ERR_INVALID_ARG && bsp_audio_get_volume()==percent);
        assert(bsp_play_audio_with_start(pcm,8,started,nullptr)==ESP_OK);
        assert((events==std::vector<std::string>{"start","write","write","delay110"}));
        if(percent==0) assert((output==std::vector<uint8_t>(8,0)));
        if(percent==100) assert((output==std::vector<uint8_t>(pcm,pcm+8)));
        if(percent==50) assert((output==std::vector<uint8_t>{0,192,255,63,0,32,0,224}));
    }
    assert(callbacks==3);
    events.clear();
    assert(bsp_play_audio_with_start(pcm,7,started,nullptr)==ESP_ERR_INVALID_ARG);
    assert(events.empty() && callbacks==3);
    assert(bsp_audio_stop()==ESP_OK);
    events.clear(); fail_enable=true;
    assert(bsp_play_audio_with_start(pcm,8,started,nullptr)==ESP_FAIL);
    assert((events==std::vector<std::string>{"enable"}) && callbacks==3);
    events.clear();fail_enable=false;fail_write=true;
    assert(bsp_play_audio_with_start(pcm,8,started,nullptr)==ESP_ERR_TIMEOUT);
    assert((events==std::vector<std::string>{"enable","delay20","start","write","delay110"}));
    assert(callbacks==4);
    events.clear(); fail_write=false;
    assert(bsp_play_audio_with_start(pcm,8,started,nullptr)==ESP_OK);
    assert((events==std::vector<std::string>{"start","write","write","delay110"}) && callbacks==5);
    // Playback volume does not alter the RX path.
    assert(bsp_audio_set_volume(0)==ESP_OK);
    int16_t mic[4]={};
    assert(bsp_board_init(16000,1,16)==ESP_OK);
    assert(bsp_get_feed_data(false,mic,sizeof(mic))==ESP_OK);
    for(int16_t value:mic) assert(value==0x5555);
    puts("PASS: real BSP simulated I2S warm-up, PCM16, partial/failure drain, callback and RX isolation; no hardware.");
}
