CC          = gcc 
CXX         = g++ 
STRIP       = strip
armCC       = arm-linux-gnueabihf-gcc
armCXX      = arm-linux-gnueabihf-g++
armSTRIP    = arm-linux-gnueabihf-strip
rpi-armCC   = /opt/tools/arm-bcm2708/arm-linux-gnueabihf/bin/arm-linux-gnueabihf-gcc
rpi-armCXX  = /opt/tools/arm-bcm2708/arm-linux-gnueabihf/bin/arm-linux-gnueabihf-g++ 
rpi-armSTRIP= /opt/tools/arm-bcm2708/arm-linux-gnueabihf/bin/arm-linux-gnueabihf-strip

CFLAGS  = -g -O3 -Wall -std=c++0x -pthread -I.
LIBS    = -lpthread
LDFLAGS = -g

BIN = dvmcmd
OBJECTS = \
		network/UDPSocket.o \
		edac/SHA256.o \
		RemoteCommand.o

all:	dvmcmd
dvmcmd: $(OBJECTS) 
		$($(ARCH)CXX) $(OBJECTS) $(CFLAGS) $(LIBS) -o $(BIN)
%.o: %.cpp
		$($(ARCH)CXX) $(CFLAGS) -c -o $@ $<
strip:
		$($(ARCH)STRIP) $(BIN)
clean:
		$(RM) $(BIN) $(OBJECTS) *.o *.d *.bak *~

