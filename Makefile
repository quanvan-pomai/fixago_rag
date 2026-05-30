# Makefile for building all submodules in fixago_rag
#
# Usage:
#   make          - Build all submodules
#   make clean    - Remove build directories and clean binaries
#   make status   - Show status of submodules

.PHONY: all clean status cheesebrain pomaidb pomaicache submodule-check help

# Determine number of processor cores for parallel build
NPROC ?= $(shell nproc 2>/dev/null || echo 4)

all: cheesebrain pomaidb pomaicache
	@echo "============================================="
	@echo " All submodules built successfully!          "
	@echo "============================================="

help:
	@echo "Available targets:"
	@echo "  make              - Build all submodules"
	@echo "  make cheesebrain  - Build cheesebrain (CMake)"
	@echo "  make pomaidb      - Build pomaidb (CMake)"
	@echo "  make pomaicache   - Build pomaicache (CMake)"
	@echo "  make clean        - Clean all builds"
	@echo "  make status       - Check git submodules status"

# Automatically initialize submodules if they are missing or empty
submodule-check:
	@if [ ! -f cheesebrain/CMakeLists.txt ] || \
	    [ ! -f pomaidb/CMakeLists.txt ] || \
	    [ ! -f pomaicache/CMakeLists.txt ]; then \
		echo "Submodules appear to be missing or uninitialized. Initializing..."; \
		git submodule update --init --recursive; \
	fi

# 1. cheesebrain
cheesebrain: submodule-check
	@echo "--- Building cheesebrain ---"
	mkdir -p cheesebrain/build
	cmake -S cheesebrain -B cheesebrain/build \
		-DCMAKE_BUILD_TYPE=Release \
		-DCHEESE_BUILD_TESTS=OFF \
		-DCHEESE_BUILD_EXAMPLES=OFF
	cmake --build cheesebrain/build -j$(NPROC)

# 2. pomaidb
pomaidb: submodule-check
	@echo "--- Building pomaidb ---"
	mkdir -p pomaidb/build
	cmake -S pomaidb -B pomaidb/build \
		-DCMAKE_BUILD_TYPE=Release \
		-DPOMAI_BUILD_TESTS=OFF \
		-DPOMAI_BUILD_BENCH=OFF
	cmake --build pomaidb/build -j$(NPROC)

# 3. pomaicache
pomaicache: submodule-check
	@echo "--- Building pomaicache ---"
	mkdir -p pomaicache/build
	pybind11_dir=$$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())"); \
	cmake -S pomaicache -B pomaicache/build \
		-DCMAKE_BUILD_TYPE=Release \
		-DBUILD_PYTHON_BINDINGS=OFF \
		-Dpybind11_DIR="$$pybind11_dir"
	cmake --build pomaicache/build -j$(NPROC)

clean:
	@echo "--- Cleaning build files ---"
	rm -rf cheesebrain/build
	rm -rf pomaidb/build
	rm -rf pomaicache/build
	@echo "Clean completed."

status:
	git submodule status --recursive
