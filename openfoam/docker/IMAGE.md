# OpenFOAM runtime

All CFD runs use the official OpenCFD runtime image, pinned by digest:

    opencfd/openfoam-run@sha256:7ad9ee415db514ecfab39718200049fac21dad4c4385c185595c08237f44929b

(tag `2606`, linux/arm64; OpenFOAM v2606, `WM_PROJECT_VERSION=v2606`). Pulled 2026-10-12.
The image is driven by `src/hwreview/foam.py`, which runs each utility as

    docker run --rm --user <uid>:<gid> -e HOME=/tmp -v <runs>:/work --entrypoint bash <image> \
        -c '. /usr/lib/openfoam/openfoam2606/etc/bashrc; cd /work/<case> && <utility> > log.<utility> 2>&1'

and fails on a non-zero exit status, on `FOAM FATAL`, or on a log that lacks `End`.
On the development machine the Docker engine is Colima (14 CPUs, 16 GB). Case
dictionaries are generated from Python (`src/hwreview/cases.py`,
`src/hwreview/verify_cfd.py`); there are no hand-edited templates.

On amd64 hosts use the amd64 digest of the same tag:
`sha256:0b0892f2fadbf5602f8fad8f8e507a81b6995863c7b021886a58ddce099e7a77`.
