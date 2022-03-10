CC        = gcc 
CXX       = g++ 
armCC     = arm-linux-gnueabihf-gcc
armCXX    = arm-linux-gnueabihf-g++
rpi-armCC = /opt/tools/arm-bcm2708/arm-linux-gnueabihf/bin/arm-linux-gnueabihf-gcc
rpi-armCXX= /opt/tools/arm-bcm2708/arm-linux-gnueabihf/bin/arm-linux-gnueabihf-g++ 

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
		$(CXX) $(OBJECTS) $(CFLAGS) $(LIBS) -o $(BIN)
%.o: %.cpp
		$(CXX) $(CFLAGS) -c -o $@ $<
clean:
		$(RM) $(BIN) $(OBJECTS) *.o *.d *.bak *~

