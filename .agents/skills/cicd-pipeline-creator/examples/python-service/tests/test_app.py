def test_example_package_version():
    from python_service import __version__

    assert __version__ == "0.1.0"
