/* hello.c - exemple minimal cc65 : valide la chaîne C (cc65 + runtime c64). */
#include <stdio.h>
#include <conio.h>
#include <peekpoke.h>

#define WITNESS_ADDR  0x02FE   /* distinct de l'exemple asm ($02FF) */
#define WITNESS_VALUE 0x43

int main(void)
{
    clrscr();
    bordercolor(COLOR_BLUE);
    bgcolor(COLOR_BLACK);
    textcolor(COLOR_WHITE);
    /* minuscules dans le source = majuscules à l'écran (conversion PETSCII) */
    printf("hello from cc65 (c)!\n");
    printf("2+2=%d\n", 2 + 2);
    POKE(WITNESS_ADDR, WITNESS_VALUE);
    for (;;) {
        /* boucle infinie : le programme reste observable */
    }
    return 0;
}
