#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <type_traits>

namespace brep_evidence {

inline std::uint32_t rotate_right(std::uint32_t value, unsigned int amount) {
    return (value >> amount) | (value << (32U - amount));
}

inline std::string sha256_hex(const std::vector<std::uint8_t>& input) {
    constexpr std::array<std::uint32_t, 64> k = {
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U,
        0x923f82a4U, 0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U,
        0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U,
        0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
        0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU,
        0x5b9cca4fU, 0x682e6ff3U, 0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
    };
    std::vector<std::uint8_t> message = input;
    const std::uint64_t bit_length = static_cast<std::uint64_t>(message.size()) * 8U;
    message.push_back(0x80U);
    while ((message.size() % 64U) != 56U) message.push_back(0U);
    for (unsigned int shift = 56U; shift != static_cast<unsigned int>(-8); shift -= 8U) {
        message.push_back(static_cast<std::uint8_t>((bit_length >> shift) & 0xffU));
        if (shift == 0U) break;
    }
    std::array<std::uint32_t, 8> state = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    };
    for (std::size_t offset = 0; offset < message.size(); offset += 64U) {
        std::array<std::uint32_t, 64> words{};
        for (unsigned int i = 0; i < 16U; ++i) {
            const std::size_t p = offset + static_cast<std::size_t>(i) * 4U;
            words[i] = (static_cast<std::uint32_t>(message[p]) << 24U) |
                       (static_cast<std::uint32_t>(message[p + 1U]) << 16U) |
                       (static_cast<std::uint32_t>(message[p + 2U]) << 8U) |
                       static_cast<std::uint32_t>(message[p + 3U]);
        }
        for (unsigned int i = 16U; i < 64U; ++i) {
            const std::uint32_t s0 = rotate_right(words[i - 15U], 7U) ^
                                     rotate_right(words[i - 15U], 18U) ^ (words[i - 15U] >> 3U);
            const std::uint32_t s1 = rotate_right(words[i - 2U], 17U) ^
                                     rotate_right(words[i - 2U], 19U) ^ (words[i - 2U] >> 10U);
            words[i] = words[i - 16U] + s0 + words[i - 7U] + s1;
        }
        auto working = state;
        for (unsigned int i = 0; i < 64U; ++i) {
            const std::uint32_t s1 = rotate_right(working[4], 6U) ^
                                     rotate_right(working[4], 11U) ^ rotate_right(working[4], 25U);
            const std::uint32_t choose = (working[4] & working[5]) ^ ((~working[4]) & working[6]);
            const std::uint32_t temp1 = working[7] + s1 + choose + k[i] + words[i];
            const std::uint32_t s0 = rotate_right(working[0], 2U) ^
                                     rotate_right(working[0], 13U) ^ rotate_right(working[0], 22U);
            const std::uint32_t majority = (working[0] & working[1]) ^
                                           (working[0] & working[2]) ^ (working[1] & working[2]);
            const std::uint32_t temp2 = s0 + majority;
            working = {temp1 + temp2, working[0], working[1], working[2],
                       working[3] + temp1, working[4], working[5], working[6]};
        }
        for (unsigned int i = 0; i < 8U; ++i) state[i] += working[i];
    }
    static constexpr char hex[] = "0123456789abcdef";
    std::string result;
    result.reserve(64U);
    for (const std::uint32_t word : state) {
        for (unsigned int shift = 24U;; shift -= 8U) {
            const auto byte = static_cast<unsigned int>((word >> shift) & 0xffU);
            result.push_back(hex[byte >> 4U]);
            result.push_back(hex[byte & 0x0fU]);
            if (shift == 0U) break;
        }
    }
    return result;
}

template <typename T>
inline void append_little_endian(std::vector<std::uint8_t>& bytes, T value) {
    static_assert(std::is_trivially_copyable_v<T>);
    std::array<std::uint8_t, sizeof(T)> raw{};
    std::memcpy(raw.data(), &value, sizeof(T));
    bytes.insert(bytes.end(), raw.begin(), raw.end());
}

}  // namespace brep_evidence
