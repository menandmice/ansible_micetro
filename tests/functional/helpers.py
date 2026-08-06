"""Shared task-builders for functional test playbooks."""


def uri_check(name, url, register, status_code=None):
    """A raw, module-independent read of the API, for verifying real
    server state rather than trusting the module under test's own
    self-reported `changed`.
    """
    return {
        "name": name,
        "ansible.builtin.uri": {
            "url": url,
            "url_username": "{{ mm_provider.mm_user }}",
            "url_password": "{{ mm_provider.mm_password }}",
            "force_basic_auth": True,
            "return_content": True,
            "status_code": status_code or [200, 404],
        },
        "register": register,
    }


def as_bool(value):
    """Ansible's templating doesn't reliably preserve native bool/int
    types through a set_fact -> to_nice_json round trip, so test_output
    values may come back as the strings "True"/"False" instead of real
    booleans. Normalize on the Python side instead of fighting that.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def collect_output(mapping):
    """mapping: output key -> Jinja expression string (no {{ }})."""
    return {
        "name": "Collect test output",
        "ansible.builtin.set_fact": {
            "test_output": {
                key: "{{ %s }}" % expr for key, expr in mapping.items()
            }
        },
    }
