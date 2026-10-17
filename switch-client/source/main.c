
#include <switch.h>
#include <stdio.h>

int main(int argc, char* argv[])
{
    consoleInit(NULL);

    printf("3DS Remote Manager\n");
    printf("------------------\n\n");
    printf("Client homebrew Switch\n\n");
    printf("Compilation reussie !\n\n");
    printf("Appuie sur + pour quitter.\n");

    while (appletMainLoop())
    {
        consoleUpdate(NULL);

        // La sortie est geree par la fermeture de l'application
        // via le bouton HOME.
    }

    consoleExit(NULL);
    return 0;
}
