#include <pybind11/pybind11.h>

#include <cerrno>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

#ifdef _WIN32
#error "native_atomic_publish currently requires POSIX filesystem primitives"
#endif

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <linux/fs.h>

namespace py = pybind11;
namespace fs = std::filesystem;

namespace {

void require_directory(const fs::path& path, const char* reason) {
    std::error_code ec;
    const fs::file_status status = fs::symlink_status(path, ec);
    if (ec || !fs::is_directory(status)) throw std::runtime_error(reason);
    if (fs::is_symlink(status)) throw std::runtime_error("stage_symlink_forbidden");
}

dev_t device_of(const fs::path& path) {
    struct stat info {};
    if (::stat(path.c_str(), &info) != 0) throw std::system_error(errno, std::generic_category(), "stat");
    return info.st_dev;
}

void fsync_path(const fs::path& path, bool directory) {
    const int flags = directory ? O_RDONLY | O_DIRECTORY : O_RDONLY;
    const int descriptor = ::open(path.c_str(), flags | O_CLOEXEC);
    if (descriptor < 0) throw std::system_error(errno, std::generic_category(), "open_for_fsync");
    const int result = ::fsync(descriptor);
    const int saved_errno = errno;
    ::close(descriptor);
    if (result != 0) throw std::system_error(saved_errno, std::generic_category(), "fsync");
}

void fsync_tree(const fs::path& root) {
    require_directory(root, "stage_root_not_directory");
    std::error_code ec;
    fs::recursive_directory_iterator iterator(root, fs::directory_options::none, ec);
    if (ec) throw std::runtime_error("stage_tree_iterate_failed");
    const fs::recursive_directory_iterator end;
    for (; iterator != end; iterator.increment(ec)) {
        if (ec) throw std::runtime_error("stage_tree_iterate_failed");
        const fs::path path = iterator->path();
        const fs::file_status status = iterator->symlink_status(ec);
        if (ec || fs::is_symlink(status)) throw std::runtime_error("stage_symlink_or_status_failure");
        if (fs::is_directory(status)) {
            fsync_path(path, true);
        } else if (fs::is_regular_file(status)) {
            fsync_path(path, false);
        } else {
            throw std::runtime_error("stage_special_file_forbidden");
        }
    }
    fsync_path(root, true);
}

void seal_stage(const std::string& stage_string) {
    fsync_tree(fs::path(stage_string));
}

bool direct_sibling(const fs::path& parent, const fs::path& child) {
    return child.parent_path().lexically_normal() == parent.lexically_normal();
}

std::string make_stage(const std::string& destination_string) {
    const fs::path destination = fs::absolute(destination_string).lexically_normal();
    const fs::path parent = destination.parent_path();
    require_directory(parent, "destination_parent_not_directory");
    std::string template_path = (parent / ".autotessell-stage-XXXXXX").string();
    std::vector<char> buffer(template_path.begin(), template_path.end());
    buffer.push_back('\0');
    char* created = ::mkdtemp(buffer.data());
    if (created == nullptr) throw std::system_error(errno, std::generic_category(), "mkdtemp");
    const fs::path stage(created);
    if (device_of(parent) != device_of(stage)) {
        fs::remove(stage);
        throw std::runtime_error("stage_destination_filesystem_mismatch");
    }
    return stage.string();
}

py::dict publish_stage(const std::string& destination_string, const std::string& stage_string) {
    const fs::path destination = fs::absolute(destination_string).lexically_normal();
    const fs::path stage = fs::absolute(stage_string).lexically_normal();
    const fs::path parent = destination.parent_path();
    require_directory(parent, "destination_parent_not_directory");
    require_directory(stage, "stage_root_not_directory");
    if (!direct_sibling(parent, stage)) throw std::runtime_error("stage_must_be_destination_sibling");
    if (device_of(parent) != device_of(stage)) throw std::runtime_error("stage_destination_filesystem_mismatch");
    std::error_code ec;
    const fs::file_status destination_status = fs::symlink_status(destination, ec);
    if (ec && ec.value() != ENOENT) throw std::runtime_error("destination_status_failed");
    const bool destination_exists = !ec && fs::exists(destination_status);
    if (destination_exists && fs::is_symlink(destination_status)) throw std::runtime_error("destination_symlink_forbidden");
    if (destination_exists && !fs::is_directory(destination_status)) throw std::runtime_error("destination_not_directory");

    fsync_tree(stage);
    fsync_path(parent, true);
    bool exchanged = false;
    if (destination_exists) {
        const long result = ::syscall(
            SYS_renameat2, AT_FDCWD, stage.c_str(), AT_FDCWD, destination.c_str(), RENAME_EXCHANGE);
        if (result != 0) throw std::system_error(errno, std::generic_category(), "atomic_exchange_unavailable");
        exchanged = true;
    } else {
        if (::rename(stage.c_str(), destination.c_str()) != 0) {
            throw std::system_error(errno, std::generic_category(), "atomic_publish_failed");
        }
    }
    fsync_path(parent, true);
    py::dict result;
    result["accepted"] = true;
    result["atomic"] = true;
    result["destination"] = destination.string();
    result["published_stage"] = destination_exists ? destination.string() : destination.string();
    if (exchanged) {
        result["rollback_backup"] = stage.string();
    } else {
        result["rollback_backup"] = py::none();
    }
    result["same_filesystem"] = true;
    result["fsynced"] = true;
    return result;
}

void discard_stage(const std::string& stage_string) {
    const fs::path stage = fs::absolute(stage_string).lexically_normal();
    if (stage.filename().string().rfind(".autotessell-stage-", 0) != 0) {
        throw std::runtime_error("stage_name_not_owned");
    }
    require_directory(stage, "stage_root_not_directory");
    fs::remove_all(stage);
    fsync_path(stage.parent_path(), true);
}

py::dict rollback_stage(const std::string& destination_string, const std::string& backup_string) {
    const fs::path destination = fs::absolute(destination_string).lexically_normal();
    const fs::path parent = destination.parent_path();
    require_directory(parent, "destination_parent_not_directory");
    require_directory(destination, "destination_root_not_directory");
    if (backup_string.empty()) {
        std::error_code ec;
        fs::remove_all(destination, ec);
        if (ec) throw std::system_error(ec, "rollback_remove_candidate_failed");
        fsync_path(parent, true);
        py::dict result;
        result["accepted"] = true;
        result["restored_baseline"] = true;
        result["rollback_backup"] = py::none();
        return result;
    }
    const fs::path backup = fs::absolute(backup_string).lexically_normal();
    if (!direct_sibling(parent, backup)) throw std::runtime_error("rollback_backup_must_be_destination_sibling");
    require_directory(backup, "rollback_backup_not_directory");
    if (device_of(parent) != device_of(backup)) throw std::runtime_error("rollback_backup_filesystem_mismatch");
    const long exchanged = ::syscall(
        SYS_renameat2, AT_FDCWD, destination.c_str(), AT_FDCWD, backup.c_str(), RENAME_EXCHANGE);
    if (exchanged != 0) throw std::system_error(errno, std::generic_category(), "atomic_rollback_exchange_failed");
    std::error_code ec;
    fs::remove_all(backup, ec);
    if (ec) throw std::system_error(ec, "rollback_discard_candidate_failed");
    fsync_path(parent, true);
    py::dict result;
    result["accepted"] = true;
    result["restored_baseline"] = true;
    result["rollback_backup"] = destination.string();
    return result;
}

}  // namespace

PYBIND11_MODULE(native_atomic_publish, module) {
    module.doc() = "C++23 fail-closed native stage and atomic directory publish kernel";
    module.def("make_stage", &make_stage, py::arg("destination"));
    module.def("seal_stage", &seal_stage, py::arg("stage"));
    module.def("publish_stage", &publish_stage, py::arg("destination"), py::arg("stage"));
    module.def("rollback_stage", &rollback_stage, py::arg("destination"), py::arg("backup"));
    module.def("discard_stage", &discard_stage, py::arg("stage"));
}
