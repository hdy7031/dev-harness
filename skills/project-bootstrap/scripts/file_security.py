"""OS serialization and a deliberately narrow file-security boundary; stdlib only."""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat

if os.name == "nt":
    import ctypes as C
    from ctypes import wintypes as W

    kernel = C.WinDLL("kernel32", use_last_error=True)
    advapi = C.WinDLL("advapi32", use_last_error=True)
    P = C.c_void_p

    def api(dll, name, args, result=W.BOOL):
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = args, result
        return fn

    get_security = api(advapi, "GetFileSecurityW", [W.LPCWSTR, W.DWORD, P, W.DWORD, P])
    set_security = api(advapi, "SetFileSecurityW", [W.LPCWSTR, W.DWORD, P])
    set_named_security = api(advapi, "SetNamedSecurityInfoW", [W.LPWSTR, W.DWORD, W.DWORD, P, P, P, P], W.DWORD)
    get_owner = api(advapi, "GetSecurityDescriptorOwner", [P, P, P])
    get_group = api(advapi, "GetSecurityDescriptorGroup", [P, P, P])
    get_dacl = api(advapi, "GetSecurityDescriptorDacl", [P, P, P, P])
    get_sacl = api(advapi, "GetSecurityDescriptorSacl", [P, P, P, P])
    get_control = api(advapi, "GetSecurityDescriptorControl", [P, P, P])
    sid_length = api(advapi, "GetLengthSid", [P], W.DWORD)
    from_sddl = api(advapi, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [W.LPCWSTR, W.DWORD, P, P])
    to_sid_text = api(advapi, "ConvertSidToStringSidW", [P, P])
    process_handle = api(kernel, "GetCurrentProcess", [], W.HANDLE)
    open_token = api(advapi, "OpenProcessToken", [W.HANDLE, W.DWORD, P])
    token_info = api(advapi, "GetTokenInformation", [W.HANDLE, C.c_int, P, W.DWORD, P])
    close_handle = api(kernel, "CloseHandle", [W.HANDLE])
    local_free = api(kernel, "LocalFree", [P], P)
    create_mutex = api(kernel, "CreateMutexW", [P, W.BOOL, W.LPCWSTR], W.HANDLE)
    wait_mutex = api(kernel, "WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
    release_mutex = api(kernel, "ReleaseMutex", [W.HANDLE])
    common_data = api(C.WinDLL("shell32", use_last_error=True), "SHGetFolderPathW",
                      [W.HWND, C.c_int, W.HANDLE, W.DWORD, W.LPWSTR], C.c_long)
    set_attributes = api(kernel, "SetFileAttributesW", [W.LPCWSTR, W.DWORD])

    def checked(ok):
        if not ok:
            raise C.WinError(C.get_last_error())
        return ok

    def descriptor(path, flags=7):
        size = W.DWORD()
        get_security(str(path), flags, None, 0, C.byref(size))
        if not size.value:
            raise C.WinError(C.get_last_error())
        buf = C.create_string_buffer(size.value)
        checked(get_security(str(path), flags, buf, size, C.byref(size)))
        return buf.raw

    def security_parts(sd):
        buf = C.create_string_buffer(sd)
        owner, group, dacl = P(), P(), P()
        defaulted, present = W.BOOL(), W.BOOL()
        control, revision = W.WORD(), W.DWORD()
        checked(get_owner(buf, C.byref(owner), C.byref(defaulted)))
        checked(get_group(buf, C.byref(group), C.byref(defaulted)))
        checked(get_dacl(buf, C.byref(present), C.byref(dacl), C.byref(defaulted)))
        checked(get_control(buf, C.byref(control), C.byref(revision)))
        # Compare ACEs, not ACL allocation padding. Inherited provenance does
        # not change the current grant; protection is compared separately.
        acl = None
        if dacl:
            aces, offset = [], 8
            for _ in range(C.c_ushort.from_address(dacl.value + 4).value):
                size = C.c_ushort.from_address(dacl.value + offset + 2).value
                ace = bytearray(C.string_at(dacl.value + offset, size))
                ace[1] &= ~0x10  # INHERITED_ACE
                aces.append(bytes(ace))
                offset += size
            acl = tuple(aces)
        return (C.string_at(owner, sid_length(owner)) if owner else None,
                C.string_at(group, sid_length(group)) if group else None,
                bool(present), acl, bool(control.value & 0x1000))

    def user_sid():
        token, size = W.HANDLE(), W.DWORD()
        checked(open_token(process_handle(), 8, C.byref(token)))
        try:
            token_info(token, 1, None, 0, C.byref(size))
            buf = C.create_string_buffer(size.value)
            checked(token_info(token, 1, buf, size, C.byref(size)))
            sid = P.from_buffer(buf)
            text = W.LPWSTR()
            checked(to_sid_text(sid, C.byref(text)))
            try:
                return text.value
            finally:
                local_free(text)
        finally:
            close_handle(token)

    def private_descriptor(directory=True):
        sd, size = P(), W.DWORD()
        checked(from_sddl(f"D:P(A;{'OICI' if directory else ''};FA;;;{user_sid()})", 1, C.byref(sd), C.byref(size)))
        try:
            return C.string_at(sd, size.value)
        finally:
            local_free(sd)

    def put_dacl(path, sd, protected=True):
        buf = C.create_string_buffer(sd)
        present, defaulted, dacl = W.BOOL(), W.BOOL(), P()
        checked(get_dacl(buf, C.byref(present), C.byref(dacl), C.byref(defaulted)))
        if not present:
            raise ValueError("Unsupported absent Windows DACL")
        if protected and dacl:
            offset = 8
            for _ in range(C.c_ushort.from_address(dacl.value + 4).value):
                C.c_ubyte.from_address(dacl.value + offset + 1).value &= ~0x10
                offset += C.c_ushort.from_address(dacl.value + offset + 2).value
        # SetFileSecurityW does not reliably apply the inheritance flags.
        error = set_named_security(str(path), 1, 4 | (0x80000000 if protected else 0x20000000),
                                   None, None, dacl, None)
        if error:
            raise C.WinError(error)

    class SecurityAttributes(C.Structure):
        _fields_ = [("length", W.DWORD), ("descriptor", P), ("inherit", W.BOOL)]

    create_directory = api(kernel, "CreateDirectoryW", [W.LPCWSTR, P])

    class StreamData(C.Structure):
        _fields_ = [("size", C.c_longlong), ("name", W.WCHAR * 296)]

    first_stream = api(kernel, "FindFirstStreamW", [W.LPCWSTR, C.c_int, P, W.DWORD], W.HANDLE)
    next_stream = api(kernel, "FindNextStreamW", [W.HANDLE, P])
    find_close = api(kernel, "FindClose", [W.HANDLE])

    def streams(path):
        result = []
        data = StreamData()
        handle = first_stream(str(path), 0, C.byref(data), 0)
        if handle == P(-1).value:
            if C.get_last_error() == 38:  # Empty file: ERROR_HANDLE_EOF.
                return result
            raise C.WinError(C.get_last_error())
        try:
            while True:
                if data.name != "::$DATA":
                    result.append((data.name, data.size))
                if not next_stream(handle, C.byref(data)):
                    if C.get_last_error() != 38:
                        raise C.WinError(C.get_last_error())
                    break
        finally:
            find_close(handle)
        return sorted(result)

    def reject_ads(path):
        if streams(path):
            raise ValueError(f"Unsupported alternate data stream (ADS): {path}")


def project_identity(root):
    info = root.stat()
    if not info.st_ino:
        raise ValueError("Filesystem cannot establish project identity")
    return hashlib.sha256(f"{info.st_dev}:{info.st_ino}".encode()).hexdigest()


def outside_worktree(path, root):
    path = path.resolve()
    if path.is_relative_to(root) or any((p / ".git").exists() for p in (path, *path.parents)):
        raise ValueError("Runtime storage must be outside Git working trees and the project")


@contextmanager
def project_lock(root):
    """Nonblocking, process-lifetime OS lock. Never unlink a live lock inode."""
    key = project_identity(root)
    if os.name == "nt":
        handle = checked(create_mutex(None, False, "Global\\dev-harness-" + key))
        acquired = False
        try:
            result = wait_mutex(handle, 0)
            acquired = result in (0, 0x80)  # Normal acquisition or abandoned owner.
            if not acquired:
                if result != 0x102:
                    raise C.WinError(C.get_last_error())
                raise ValueError("Project helper busy: execution lock held by another process")
            yield
        finally:
            if acquired:
                checked(release_mutex(handle))
            close_handle(handle)
    elif os.name == "posix":
        import fcntl
        # A fixed host namespace avoids splitting locks by user-specific TMPDIR.
        lock_path = Path("/tmp") / ("dev-harness-" + key + ".lock")
        outside_worktree(lock_path, root)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Unsafe project execution lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Project helper busy: execution lock held by another process") from exc
            yield
        finally:
            os.close(fd)
    else:
        raise ValueError("No supported OS project lock")


def private_directory(path):
    if os.name == "nt":
        expected = private_descriptor()
        buf = C.create_string_buffer(expected)
        attrs = SecurityAttributes(C.sizeof(SecurityAttributes), C.cast(buf, P), False)
        if not create_directory(str(path), C.byref(attrs)) and C.get_last_error() != 183:
            raise C.WinError(C.get_last_error())
        if path.is_symlink() or path.lstat().st_file_attributes & 0x400 or not path.is_dir():
            raise ValueError("Unsafe private storage directory")
        actual = security_parts(descriptor(path))
        # Owner defaults to the creator; compare it with a new descriptor's token SID.
        sid = W.LPWSTR()
        owner = C.create_string_buffer(actual[0])
        checked(to_sid_text(owner, C.byref(sid)))
        try:
            if sid.value != user_sid() or actual[2:] != security_parts(expected)[2:]:
                raise ValueError("Private recovery storage has unexpected owner/DACL")
        finally:
            local_free(sid)
    else:
        path.mkdir(mode=0o700, exist_ok=True)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Private recovery storage has unexpected owner/mode")


def storage_candidates(root):
    """Deterministic same-filesystem locations, independent of TEMP and user."""
    if os.name == "nt":
        folder = C.create_unicode_buffer(260)
        if common_data(None, 0x23, None, 0, folder) != 0:  # CSIDL_COMMON_APPDATA.
            raise OSError("Cannot locate OS common application data")
        parent = Path(folder.value).resolve()
    else:
        parent = Path("/tmp")
    name = "dev-harness-" + project_identity(root)
    legacy = parent / name
    candidates = []
    for parent in (parent, *root.parents):
        base = parent / name
        try:
            outside_worktree(base, root)
        except ValueError:
            continue  # A nested repository needs an ancestor outside the outer tree.
        if parent.stat().st_dev == root.stat().st_dev and base not in candidates:
            candidates.append(base)
    return legacy, candidates


def storage(root, create=True):
    legacy, candidates = storage_candidates(root)
    # Never hide 0.3.0 recovery evidence, including an old cross-volume container.
    if legacy not in candidates and legacy.exists():
        private_directory(legacy)
        if any(legacy.iterdir()):
            return legacy
    existing = [base for base in candidates if base.exists()]
    if len(existing) > 1:
        raise ValueError("Multiple project state roots; review recovery storage before retrying")
    if existing:
        # Permission drift is a hard failure, not permission to fork recovery state.
        private_directory(existing[0])
        return existing[0]
    if not candidates:
        raise ValueError("No same-filesystem private storage outside Git working trees")
    if not create:
        return candidates[0]
    failures = []
    for base in candidates:
        try:
            private_directory(base)
            return base
        except PermissionError as exc:
            if base.exists():
                raise  # An existing but unverifiable container must not be bypassed.
            failures.append(str(exc))
    raise PermissionError("No writable same-filesystem state root outside Git; " + "; ".join(failures))


def metadata(path):
    """Only access metadata we can reproduce. Reject known destructive cases."""
    info = path.stat()
    if info.st_nlink != 1:
        raise ValueError(f"Unsupported hardlinked output: {path}")
    if os.name == "nt":
        if info.st_file_attributes & ~(0x20 | 0x80):
            raise ValueError(f"Unsupported Windows file attributes: {path}")
        reject_ads(path)
        # Mandatory integrity labels affect access beyond the DACL. Do not
        # replace explicitly labelled files with an unlabelled stage.
        label = C.create_string_buffer(descriptor(path, 0x10))
        present, defaulted, acl = W.BOOL(), W.BOOL(), P()
        checked(get_sacl(label, C.byref(present), C.byref(acl), C.byref(defaulted)))
        if present and acl and C.c_ushort.from_address(acl.value + 4).value:
            raise ValueError(f"Unsupported Windows integrity label: {path}")
        return descriptor(path)
    if (info.st_uid != os.getuid() or info.st_mode & 0o7000 or getattr(info, "st_flags", 0)
            or not hasattr(os, "listxattr") or os.listxattr(path)):
        raise ValueError(f"Unsupported owner/extended metadata: {path}")
    return (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))


def secure_file(path):
    """Create an empty exclusive file and prove access metadata before writing payload."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    if os.name == "nt":
        checked(set_attributes(str(path), 0x80))  # Normalize only this new, empty artifact.
    if os.name == "nt":
        put_dacl(path, private_descriptor(False))
        if security_parts(descriptor(path))[2:] != security_parts(private_descriptor(False))[2:]:
            raise ValueError(f"Cannot secure private recovery payload: {path}")
    # Source permissions are recovery DATA, never payload access permissions.


def apply_metadata(path, original_metadata, protect=None):
    if os.name == "nt":
        expected = security_parts(original_metadata)
        if security_parts(descriptor(path))[:2] != expected[:2]:
            raise ValueError(f"Cannot preserve Windows owner/group: {path}")
        put_dacl(path, original_metadata, expected[4] if protect is None else protect)
        verify_metadata(path, original_metadata, protect)
    else:
        uid, gid, mode = original_metadata
        os.chown(path, uid, gid)
        os.chmod(path, mode)
        if metadata(path) != original_metadata:
            raise ValueError(f"Cannot preserve POSIX access metadata: {path}")


def verify_metadata(path, expected, protect=None):
    actual = metadata(path)
    if os.name == "nt":
        desired = security_parts(expected)
        if protect is not None:
            desired = (*desired[:4], protect)
        different = security_parts(actual) != desired
    else:
        different = actual != expected
    if different:
        raise OSError(f"File access metadata changed: {path}")


def metadata_record(value):
    return {"windows_descriptor": value.hex()} if os.name == "nt" else {"posix_access": list(value)}


def access_state(value, protect=None):
    if os.name == "nt":
        owner, group, present, acl, protected = security_parts(value)
        return {"owner": owner.hex() if owner else None, "group": group.hex() if group else None,
                "dacl_present": present, "dacl": [ace.hex() for ace in acl] if acl is not None else None,
                "dacl_protected": protected if protect is None else protect}
    return dict(zip(("owner", "group", "mode"), value))


def file_state(path):
    """JSON-safe fingerprint; observe unsupported metadata rather than reject it.

    Drift must remain observable during rollback (notably a newly created ADS).
    This is the supported replacement boundary, not a full NTFS snapshot.
    """
    if not path.exists():
        return None
    info = path.lstat()
    result = {"main_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "links": info.st_nlink}
    if os.name == "nt":
        result.update(access_state(descriptor(path)))
        result.update(attributes=info.st_file_attributes, ads=[list(entry) for entry in streams(path)])
        label = C.create_string_buffer(descriptor(path, 0x10))
        present, defaulted, acl = W.BOOL(), W.BOOL(), P()
        checked(get_sacl(label, C.byref(present), C.byref(acl), C.byref(defaulted)))
        result["integrity_label"] = (C.string_at(acl, C.c_ushort.from_address(acl.value + 2).value).hex()
                                     if present and acl else None)
    else:
        result.update(access_state((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))))
        result.update(flags=getattr(info, "st_flags", 0),
                      xattrs={name: os.getxattr(path, name).hex() for name in sorted(os.listxattr(path))})
    return result


def state_drift(current, expected):
    if current is None or expected is None:
        return [] if current == expected else ["existence"]
    return [key for key in sorted(current.keys() | expected.keys()) if current.get(key) != expected.get(key)]


def prove_replacement_metadata(path, original_metadata):
    """Empty probe only: prove owner/group, equivalent grants AND protection.

    Callers keep payloads private and install the proven DACL only after rename.
    """
    try:
        secure_file(path)
        apply_metadata(path, original_metadata, protect=True if os.name == "nt" else None)
    finally:
        path.unlink(missing_ok=True)
