// game/cString.cpp: a minimal owning string (cString) used by the debug tools: heap copies made
// with new[], the empty string shared as the literal "".

#include "types.h"
#include "cString.h"
#include <string.h>

// Empty string.
cString::cString()
{
    m_str = "";
}

// Copy of `s` (NULL / empty stays the shared empty string).
cString::cString(const char* s)
{
    m_str = "";
    if (s != NULL) {
        if (strlen(s) != 0) {
            copy(s);
        }
    }
}

// Frees the copy.
cString::~cString()
{
    clear();
}

// Replaces the contents with a copy of `o`.
cString& cString::operator=(const cString& o)
{
    if (this != &o) {
        clear();
        if (((cString&) o).size() != 0) {
            copy(((cString&) o).c_str());
        }
    }
    return *this;
}

// Appends `o` (rebuilds the buffer).
cString& cString::operator+=(const cString& o)
{
    u32 len = size() + ((cString&) o).size();
    char* buf = new char[len + 1];

    strcpy(buf, c_str());
    strcat(buf, ((cString&) o).c_str());
    clear();
    copy(buf);
    delete[] buf;
    return *this;
}

// Appends a C string.
cString& cString::operator+=(const char* s)
{
    cString tmp(s);

    return *this += tmp;
}

// The C string.
char* cString::c_str()
{
    return m_str;
}

// Length in bytes.
u32 cString::size()
{
    return strlen(m_str);
}

// Frees the copy and returns to the empty string.
void cString::clear()
{
    if (m_str != "") {
        delete[] m_str;
        m_str = "";
    }
}

// Takes a fresh heap copy of `s` (the previous buffer must already be cleared).
void cString::copy(const char* str)
{
    char* p = new char[strlen(str) + 1];

    strcpy(p, str);
    m_str = p;
}
