#!/bin/bash
do_fullpidof()
{
    APID=`ps -eo pid,cmd | grep -v grep | grep -v sh | grep $1 | cut -d' ' -f1`
    if [ ${#APID} -ne 0 ]
    then
        echo ${APID}
        return 1
    else
        APID=`ps -eo pid,cmd | grep -v grep | grep -v sh | grep $1 | cut -d' ' -f2`
        if [ ${#APID} -ne 0 ]; then
            echo ${APID}
            return 1
        else
            APID=`ps -eo pid,cmd | grep -v grep | grep -v sh | grep $1 | cut -d' ' -f3`
            if [ ${#APID} -ne 0 ]; then
                echo ${APID}
                return 1
            fi
        fi
        return 0
    fi
}

pid=$(do_fullpidof fne_bridge)
kill -9 $pid

R_PATH=/opt/dvmfne
pushd ${R_PATH}

PYTHON="/usr/bin/env python"
${PYTHON} ${R_PATH}/fne_bridge.py -c ${R_PATH}/cfg/fne_bridge.cfg &

popd
