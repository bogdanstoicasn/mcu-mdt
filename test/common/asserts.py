def assert_eq(actual, expected, **context):
    if actual != expected:
        msg = [f"Expected: {expected}", f"Actual:   {actual}"]

        for key, value in context.items():
            if isinstance(value, bytes):
                value = value.hex()
            msg.append(f"{key}: {value}")

        raise AssertionError("\n".join(msg))