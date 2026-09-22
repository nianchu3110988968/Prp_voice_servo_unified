#pragma once
#include "esp_err.h"
#include <stddef.h>
enum { HTTP_EVENT_ON_DATA, HTTP_EVENT_HEADERS_SENT, HTTP_EVENT_ON_FINISH, HTTP_EVENT_ON_HEADER };
struct esp_http_client_event_t { int event_id; void *user_data; int data_len; void *data; const char *header_key; const char *header_value; };
struct esp_http_client_config_t {
    const char *url;
    int timeout_ms;
    esp_err_t (*event_handler)(esp_http_client_event_t *);
    void *user_data;
};
typedef esp_http_client_config_t *esp_http_client_handle_t;
esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *);
esp_err_t esp_http_client_set_header(esp_http_client_handle_t, const char *, const char *);
esp_err_t esp_http_client_perform(esp_http_client_handle_t);
int esp_http_client_get_status_code(esp_http_client_handle_t);
esp_err_t esp_http_client_cleanup(esp_http_client_handle_t);
