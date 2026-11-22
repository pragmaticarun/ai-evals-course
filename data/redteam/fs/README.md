# Fake file tree (module 10)

`read_file` serves `workspace/`. `secrets/` sits next to it so that a path-traversal attack has something to reach; it holds only a canary string.
