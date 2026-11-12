.DEFAULT_GOAL := help

PROJECT_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
export PATH := $(PROJECT_ROOT)/.tools/node_modules/node/bin:$(PATH)

.PHONY: help bootstrap build dev dev-postgres test test-unit test-runtime frontend-build plugin-check check e2e smoke

help:
	@printf '%s\n' \
	  'bootstrap       安装锁定依赖并构建 Harness（需要网络）' \
	  'build           重建插件、前端和运行时清单（不安装依赖）' \
	  'dev             启动本机工作台与 Worker（SQLite）' \
	  'dev-postgres    启动本机工作台与隔离 PostgreSQL（macOS ARM64）' \
	  'check           业务/迁移测试、前端构建和插件类型检查' \
	  'test            全部后端测试（需要已构建的 Harness）' \
	  'test-unit       后端业务与迁移测试' \
	  'test-runtime    Harness 组合测试（需要已构建的 Harness）' \
	  'frontend-build  前端类型检查并构建' \
	  'plugin-check    插件严格类型检查（需要已构建的 Harness）' \
	  'e2e             浏览器测试（需先启动本机服务和安装 Chrome）' \
	  'smoke           创建合成项目并提交任务（需先启动本机服务）'

bootstrap:
	python3 infra/bootstrap.py --install --build-harness

build:
	python3 infra/bootstrap.py

dev:
	python3 infra/dev.py

dev-postgres:
	python3 infra/dev.py --postgres

test:
	cd backend && .venv/bin/python -m pytest -q

test-unit:
	cd backend && .venv/bin/python -m pytest -q --ignore=tests/test_harness_composition.py

test-runtime:
	cd backend && .venv/bin/python -m pytest -q tests/test_harness_composition.py

frontend-build:
	cd frontend && npm run build

plugin-check:
	cd runtime/bid-plugin && node typecheck.mjs

check: test-unit frontend-build plugin-check

e2e:
	cd frontend && npm test

smoke:
	backend/.venv/bin/python infra/smoke.py
