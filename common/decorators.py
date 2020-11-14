def enum_for_django(cls):
    cls.do_not_call_in_templates = True
    return cls
