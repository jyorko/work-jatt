FROM ghcr.io/joshyorko/room-of-requirement:wolfi

USER root
RUN test -f /usr/share/zoneinfo/Etc/UTC \
    && ln -snf /usr/share/zoneinfo/Etc/UTC /etc/localtime

USER vscode
