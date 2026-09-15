#include "touch_inputs.h"

#include "driver/gpio.h"

esp_err_t TouchInputs::init() {
    gpio_config_t io_conf = {};
    io_conf.pin_bit_mask = (1ULL << TOUCH_1_PIN) | (1ULL << TOUCH_2_PIN) | (1ULL << TOUCH_3_PIN);
    io_conf.mode = GPIO_MODE_INPUT;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.intr_type = GPIO_INTR_DISABLE;
    return gpio_config(&io_conf);
}

TouchEvent TouchInputs::poll() {
    const int now_1 = gpio_get_level(TOUCH_1_PIN);
    const int now_2 = gpio_get_level(TOUCH_2_PIN);
    const int now_3 = gpio_get_level(TOUCH_3_PIN);

    TouchEvent event = TouchEvent::None;
    if (now_1 == 1 && last_1_ == 0) {
        event = TouchEvent::Touch1;
    } else if (now_2 == 1 && last_2_ == 0) {
        event = TouchEvent::Touch2;
    } else if (now_3 == 1 && last_3_ == 0) {
        event = TouchEvent::Touch3;
    }

    last_1_ = now_1;
    last_2_ = now_2;
    last_3_ = now_3;
    return event;
}
