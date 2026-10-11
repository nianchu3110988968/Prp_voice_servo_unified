#pragma once

#include <stdio.h>
#include <string.h>

struct AudioVolumeCommand {
    char id[33] = {};
    bool set = false;
    int percent = -1;
    const char *error = "invalid_command";
};

// The serial reader removes CR/LF. Only ASCII identifiers can reach JSON output.
// Strict decimal input rejects signs, decimals, suffixes, overflow and extra tokens.
inline AudioVolumeCommand parse_audio_volume_command(const char *line) {
    AudioVolumeCommand result;
    if (!line || strlen(line) > 94 || strncmp(line, "volume ", 7) != 0) return result;
    char action[8] = {}, id[33] = {}, value[16] = {}, extra = 0;
    const int fields = sscanf(line, "volume %7s %32s %15s %c", action, id, value, &extra);
    if (fields < 2) return result;
    for (const char *p = id; *p; ++p) {
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || *p == '_' || *p == '-')) return result;
    }
    strcpy(result.id, id);
    if (strcmp(action, "get") == 0 && fields == 2) {
        result.error = nullptr;
        return result;
    }
    if (strcmp(action, "set") != 0 || fields != 3) return result;
    result.set = true;
    result.error = "invalid_value";
    int percent = 0;
    for (const char *p = value; *p; ++p) {
        if (*p < '0' || *p > '9') return result;
        percent = percent * 10 + (*p - '0');
        if (percent > 100) return result;
    }
    result.percent = percent;
    result.error = nullptr;
    return result;
}
