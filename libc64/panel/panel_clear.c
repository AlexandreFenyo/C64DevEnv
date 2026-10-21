/* panel_clear : remplit le panneau d'espaces (les couleurs ne changent pas). */
#include <string.h>
#include "libc64.h"

void panel_clear(void)
{
    memset(PANEL_SCREEN + PANEL_ROW * 40, ' ', PANEL_ROWS * 40);
}
