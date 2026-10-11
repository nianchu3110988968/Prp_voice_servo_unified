#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
typedef void *i2s_chan_handle_t;
typedef int i2s_data_bit_width_t;
enum { I2S_NUM_0, I2S_NUM_1, I2S_ROLE_MASTER, I2S_CLK_SRC_DEFAULT, I2S_MCLK_MULTIPLE_256,
       I2S_SLOT_MODE_MONO, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_LEFT, I2S_GPIO_UNUSED=-1,
       I2S_DATA_BIT_WIDTH_16BIT=16, I2S_DATA_BIT_WIDTH_32BIT=32 };
struct i2s_chan_config_t { int port; int dma_desc_num; int dma_frame_num; bool auto_clear_after_cb; };
#define I2S_CHANNEL_DEFAULT_CONFIG(port, role) {port, 0, 0, false}
struct TestSlot { int bit_width; int slot_mode; int slot_mask; };
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(bits, mode) {bits, mode, 0}
struct i2s_std_config_t {
    struct { uint32_t sample_rate_hz; int clk_src; int mclk_multiple; } clk_cfg;
    TestSlot slot_cfg;
    struct { int mclk,bclk,ws,dout,din; struct { bool mclk_inv,bclk_inv,ws_inv; } invert_flags; } gpio_cfg;
};
esp_err_t i2s_new_channel(const i2s_chan_config_t *, i2s_chan_handle_t *, i2s_chan_handle_t *);
esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t, const i2s_std_config_t *);
esp_err_t i2s_channel_enable(i2s_chan_handle_t);
esp_err_t i2s_channel_disable(i2s_chan_handle_t);
esp_err_t i2s_channel_write(i2s_chan_handle_t, const void *, size_t, size_t *, uint32_t);
esp_err_t i2s_channel_read(i2s_chan_handle_t, void *, size_t, size_t *, uint32_t);
