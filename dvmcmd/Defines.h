/**
* Digital Voice Modem - Remote Command Client
* GPLv2 Open Source. Use is subject to license terms.
* DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
*
* @package DVM / Remote Command Client
*
*/
//
// Based on code from the MMDVMHost project. (https://github.com/g4klx/MMDVMHost)
// Licensed under the GPLv2 License (https://opensource.org/licenses/GPL-2.0)
//
/*
*   Copyright (C) 2015,2016,2017 by Jonathan Naylor G4KLX
*   Copyright (C) 2018,2019 by Bryan Biedenkapp <gatekeep@gmail.com>
*
*   This program is free software; you can redistribute it and/or modify
*   it under the terms of the GNU General Public License as published by
*   the Free Software Foundation; either version 2 of the License, or
*   (at your option) any later version.
*
*   This program is distributed in the hope that it will be useful,
*   but WITHOUT ANY WARRANTY; without even the implied warranty of
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
*   GNU General Public License for more details.
*
*   You should have received a copy of the GNU General Public License
*   along with this program; if not, write to the Free Software
*   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
*/
#if !defined(__DEFINES_H__)
#define __DEFINES_H__

#include <stdint.h>

// ---------------------------------------------------------------------------
//  Types
// ---------------------------------------------------------------------------

#ifndef _INT8_T_DECLARED
#ifndef __INT8_TYPE__
typedef signed char         int8_t;
#endif // __INT8_TYPE__
#endif // _INT8_T_DECLARED
#ifndef _INT16_T_DECLARED
#ifndef __INT16_TYPE__
typedef short               int16_t;
#endif // __INT16_TYPE__
#endif // _INT16_T_DECLARED
#ifndef _INT32_T_DECLARED
#ifndef __INT32_TYPE__
typedef int                 int32_t;
#endif // __INT32_TYPE__
#endif // _INT32_T_DECLARED
#ifndef _INT64_T_DECLARED
#ifndef __INT64_TYPE__
typedef long long           int64_t;
#endif // __INT64_TYPE__
#endif // _INT64_T_DECLARED
#ifndef _UINT8_T_DECLARED
#ifndef __UINT8_TYPE__
typedef unsigned char       uint8_t;
#endif // __UINT8_TYPE__
#endif // _UINT8_T_DECLARED
#ifndef _UINT16_T_DECLARED
#ifndef __UINT16_TYPE__
typedef unsigned short      uint16_t;
#endif // __UINT16_TYPE__
#endif // _UINT16_T_DECLARED
#ifndef _UINT32_T_DECLARED
#ifndef __UINT32_TYPE__
typedef unsigned int        uint32_t;
#endif // __UINT32_TYPE__
#endif // _UINT32_T_DECLARED
#ifndef _UINT64_T_DECLARED
#ifndef __UINT64_TYPE__
typedef unsigned long long  uint64_t;
#endif // __UINT64_TYPE__
#endif // _UINT64_T_DECLARED

#ifndef __LONG64_TYPE__
typedef long long           long64_t;
#endif // __LONG64_TYPE__
#ifndef __ULONG64_TYPE__
typedef unsigned long long  ulong64_t;
#endif // __ULONG64_TYPE__

// ---------------------------------------------------------------------------
//  Constants
// ---------------------------------------------------------------------------

#define __PROG_NAME__ "Digital Voice Modem (DVM) RCON Tool"
#define __EXE_NAME__ "dvmcmd"
#define __VER__ "D01.00"
#define __BUILD__ __DATE__ " " __TIME__

#define HOST_SW_API 

const uint32_t RCON_DEFAULT_PORT = 9990;

// ---------------------------------------------------------------------------
//  Macros
// ---------------------------------------------------------------------------

/**
 * Property Creation
 *  These macros should always be used LAST in the "public" section of a class definition.
 */
 /// <summary>Creates a read-only get property.</summary>
#define __READONLY_PROPERTY(type, variableName, propName)                               \
        private: type m_##variableName;                                                 \
        public: __forceinline type get##propName(void) const { return m_##variableName; }
/// <summary>Creates a read-only get property, does not use "get".</summary>
#define __READONLY_PROPERTY_PLAIN(type, variableName, propName)                         \
        private: type m_##variableName;                                                 \
        public: __forceinline type propName(void) const { return m_##variableName; }
/// <summary>Creates a read-only get property by reference.</summary>
#define __READONLY_PROPERTY_BYREF(type, variableName, propName)                         \
        private: type m_##variableName;                                                 \
		public: __forceinline type& get##propName(void) const { return m_##variableName; }

/// <summary>Creates a get and set property.</summary>
#define __PROPERTY(type, variableName, propName)                                        \
        private: type m_##variableName;                                                 \
		public: __forceinline type get##propName(void) const { return m_##variableName; } \
				__forceinline void set##propName(type val) { m_##variableName = val; }
/// <summary>Creates a get and set property, does not use "get"/"set".</summary>
#define __PROPERTY_PLAIN(type, variableName, propName)                                  \
        private: type m_##variableName;                                                 \
		public: __forceinline type propName(void) const { return m_##variableName; }    \
				__forceinline void propName(type val) { m_##variableName = val; }
/// <summary>Creates a get and set property by reference.</summary>
#define __PROPERTY_BYREF(type, variableName, propName)                                  \
        private: type m_##variableName;                                                 \
		public: __forceinline type& get##propName(void) const { return m_##variableName; } \
		        __forceinline void set##propName(type& val) { m_##variableName = val; }

#endif // __DEFINES_H__
