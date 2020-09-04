#!/bin/bash
R_PATH=/opt/dvmfne
pushd ${R_PATH}

PYTHON="/usr/bin/env python"
${PYTHON} ${R_PATH}/fne_parrot.py -c ${R_PATH}/cfg/fne_parrot.cfg &
${PYTHON} ${R_PATH}/fne_router.py -c ${R_PATH}/cfg/fne_router.cfg &

popd
