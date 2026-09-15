#pragma once

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t wifi_manager_start(void);
bool wifi_manager_is_connected(void);
const char *wifi_manager_status_text(void);

#ifdef __cplusplus
}
#endif
