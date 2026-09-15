#pragma once

#include "esp_err.h"
#include "robot_config.h"

enum class TouchEvent {
    None,
    Touch1,
    Touch2,
    Touch3,
};

class TouchInputs {
public:
    esp_err_t init();
    TouchEvent poll();

private:
    int last_1_ = 0;
    int last_2_ = 0;
    int last_3_ = 0;
};
