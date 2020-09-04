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

pid=$(do_fullpidof web_tables)
kill -9 $pid

L_PATH=/opt/dvmfne/log
R_PATH=/opt/dvmfne/monitor
pushd ${R_PATH}

PYTHON="/usr/bin/env python"
${PYTHON} ${R_PATH}/web_tables.py >${L_PATH}/monitor.log 2>&1 &

popd
