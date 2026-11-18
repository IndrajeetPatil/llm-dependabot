// Minimal launcher that launchd starts instead of /bin/zsh.
//
// macOS privacy protection (TCC) blocks launchd jobs from reading ~/Documents
// unless the job's executable has Full Disk Access. Granting that to this
// dedicated binary, rather than to /bin/zsh, keeps the permission narrow.
// The command runs as a child process (not via exec) so that this binary stays
// the "responsible process" TCC checks for everything the job starts.

#include <errno.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <sys/wait.h>

extern char **environ;

static pid_t child;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s program [args...]\n", argv[0]);
        return 64;
    }
    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);

    int err = posix_spawn(&child, argv[1], NULL, NULL, &argv[1], environ);
    if (err != 0) {
        perror("posix_spawn");
        return 127;
    }
    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) {
            perror("waitpid");
            return 1;
        }
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 128 + WTERMSIG(status);
}
