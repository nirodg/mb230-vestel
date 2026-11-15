#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

int main(void) {
    FILE *proof;
    time_t now = time(NULL);

    printf("Hello, world from MB230!\n");
    printf("pid=%d uid=%d gid=%d\n", (int)getpid(), (int)getuid(), (int)getgid());
    fflush(stdout);

    proof = fopen("/tmp/hello_world_proof.txt", "w");
    if (proof) {
        fprintf(proof, "Hello, world from MB230!\n");
        fprintf(proof, "pid=%d uid=%d gid=%d\n", (int)getpid(), (int)getuid(), (int)getgid());
        if (now != (time_t)-1) {
            fprintf(proof, "time=%ld\n", (long)now);
        }
        fclose(proof);
        printf("proof written to /tmp/hello_world_proof.txt\n");
    } else {
        perror("fopen /tmp/hello_world_proof.txt");
    }

    return 0;
}
