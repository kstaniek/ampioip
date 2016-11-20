
def frame_to_str(data):
    """Convert raw data to formated string."""
    str = ":".join("{:02x}".format(c) for c in data)
    return str
