FetchContent_Declare(doctest
    GIT_REPOSITORY https://github.com/doctest/doctest.git
    GIT_TAG        v2.4.11
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(doctest)

add_executable(tessell_tests
    test_mesh2d.cpp
    test_of_writer.cpp
)
target_link_libraries(tessell_tests
    PRIVATE tessell_mesh_core doctest::doctest
)
include(doctest)
doctest_discover_tests(tessell_tests)
