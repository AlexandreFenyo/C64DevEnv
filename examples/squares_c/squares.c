/* squares.c - exemple C pour le pas à pas (VS Code, portail) : fonction
   avec paramètre, variables locales, globale et statique. Rend la main au
   BASIC à la fin (RUN pour recommencer). */
#include <stdio.h>
#include <conio.h>

unsigned char counter;          /* globale */
static int total;               /* statique du fichier */

static int square(int n)
{
    int r;

    r = n * n;
    return r;
}

int main(void)
{
    unsigned char i;
    int s;

    clrscr();
    total = 0;
    for (i = 1; i <= 5; ++i) {
        s = square(i);
        total += s;
        ++counter;
        printf("%d^2=%d\n", i, s);
    }
    printf("total=%d\n", total);
    return 0;
}
