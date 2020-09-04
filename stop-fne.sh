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

pid=$(do_fullpidof fne_router)
kill -9 $pid

pid=$(do_fullpidof fne_parrot)
kill -9 $pid
