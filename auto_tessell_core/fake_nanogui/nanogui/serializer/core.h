// Minimal NanoGUI serializer stub — allows building robust_hex_dominant_meshing
// without NanoGUI. Serializer is declared but never called in batch/headless mode.
#pragma once
#include <string>

namespace nanogui {

class Serializer {
public:
    Serializer(const std::string &, bool) {}

    template <typename T>
    bool get(const std::string &, T &) { return false; }

    template <typename T>
    void set(const std::string &, const T &) {}

    void push(const std::string &) {}
    void pop() {}
    bool isValid() const { return false; }
};

} // namespace nanogui
