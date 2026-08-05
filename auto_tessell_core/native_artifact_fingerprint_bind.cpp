#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "brep_evidence_sha256.hpp"

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;
namespace fs = std::filesystem;

namespace {

struct Entry {
    std::string relative_path;
    std::string kind;
    std::uintmax_t size{};
    std::string sha256;
};

std::vector<std::uint8_t> read_bytes(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("artifact_file_open_failed:" + path.string());
    stream.seekg(0, std::ios::end);
    const auto end = stream.tellg();
    if (end < 0) throw std::runtime_error("artifact_file_size_failed:" + path.string());
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(end));
    stream.seekg(0, std::ios::beg);
    if (!bytes.empty()) {
        stream.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        if (!stream) throw std::runtime_error("artifact_file_read_failed:" + path.string());
    }
    return bytes;
}

std::string relative_name(const fs::path& root, const fs::path& path) {
    const fs::path relative = path.lexically_relative(root);
    if (relative.empty() || relative == fs::path(".") || relative.is_absolute()) {
        throw std::runtime_error("artifact_relative_path_invalid:" + path.string());
    }
    for (const auto& component : relative) {
        if (component == fs::path("..")) throw std::runtime_error("artifact_root_escape:" + path.string());
    }
    return relative.generic_string();
}

std::vector<Entry> collect_entries(const fs::path& root) {
    std::vector<Entry> entries;
    std::error_code ec;
    const fs::file_status root_status = fs::symlink_status(root, ec);
    if (ec || !fs::is_directory(root_status)) throw std::runtime_error("artifact_root_not_directory");
    if (fs::is_symlink(root_status)) throw std::runtime_error("artifact_root_symlink");

    fs::recursive_directory_iterator iterator(root, fs::directory_options::none, ec);
    if (ec) throw std::runtime_error("artifact_tree_open_failed");
    const fs::recursive_directory_iterator end;
    for (; iterator != end; iterator.increment(ec)) {
        if (ec) throw std::runtime_error("artifact_tree_iterate_failed");
        const fs::path path = iterator->path();
        const fs::file_status status = iterator->symlink_status(ec);
        if (ec) throw std::runtime_error("artifact_status_failed:" + path.string());
        if (fs::is_symlink(status)) {
            throw std::runtime_error("artifact_symlink_forbidden:" + relative_name(root, path));
        }
        Entry entry;
        entry.relative_path = relative_name(root, path);
        if (fs::is_directory(status)) {
            entry.kind = "directory";
            entry.size = 0;
            entry.sha256 = brep_evidence::sha256_hex({});
        } else if (fs::is_regular_file(status)) {
            entry.kind = "regular";
            entry.size = fs::file_size(path, ec);
            if (ec) throw std::runtime_error("artifact_file_size_failed:" + path.string());
            entry.sha256 = brep_evidence::sha256_hex(read_bytes(path));
        } else {
            throw std::runtime_error("artifact_special_file_forbidden:" + entry.relative_path);
        }
        entries.push_back(std::move(entry));
    }
    std::sort(entries.begin(), entries.end(), [](const Entry& left, const Entry& right) {
        return left.relative_path < right.relative_path;
    });
    for (std::size_t index = 1; index < entries.size(); ++index) {
        if (entries[index - 1].relative_path == entries[index].relative_path) {
            throw std::runtime_error("artifact_duplicate_relative_path:" + entries[index].relative_path);
        }
    }
    return entries;
}

py::dict fingerprint_tree(const std::string& root_string) {
    const fs::path root = fs::absolute(fs::path(root_string)).lexically_normal();
    const auto entries = collect_entries(root);
    std::vector<std::uint8_t> canonical;
    py::list records;
    for (const Entry& entry : entries) {
        const std::string nul(1, '\0');
        const std::string record = entry.relative_path + nul + entry.kind + nul +
            std::to_string(entry.size) + nul + entry.sha256 + "\n";
        canonical.insert(canonical.end(), record.begin(), record.end());
        py::dict value;
        value["path"] = entry.relative_path;
        value["kind"] = entry.kind;
        value["size"] = entry.size;
        value["sha256"] = entry.sha256;
        records.append(value);
    }
    py::dict result;
    result["root"] = root.generic_string();
    result["entries"] = records;
    result["entry_count"] = entries.size();
    result["tree_sha256"] = brep_evidence::sha256_hex(canonical);
    result["symlinks_forbidden"] = true;
    result["special_files_forbidden"] = true;
    return result;
}

std::string sha256_bytes(py::bytes value) {
    const std::string raw = value;
    std::vector<std::uint8_t> bytes(raw.begin(), raw.end());
    return brep_evidence::sha256_hex(bytes);
}

}  // namespace

PYBIND11_MODULE(native_artifact_fingerprint, module) {
    module.doc() = "C++23 staged artifact-tree fingerprint kernel";
    module.attr("algorithm") = "SHA-256";
    module.attr("implementation") = "native_artifact_fingerprint";
    module.def("fingerprint_tree", &fingerprint_tree, py::arg("root"));
    module.def("sha256_bytes", &sha256_bytes, py::arg("value"));
}
