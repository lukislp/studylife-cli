## [1.9.4](https://github.com/lukislp/studylife-cli/compare/v1.9.3...v1.9.4) (2026-09-20)


### Bug Fixes

* **ci:** add Harden Runner in audit mode to every job ([#42](https://github.com/lukislp/studylife-cli/issues/42)) ([be13fec](https://github.com/lukislp/studylife-cli/commit/be13fec38dc3418643f6f5a8b05e288df2ebd34f))

## [1.9.3](https://github.com/lukislp/studylife-cli/compare/v1.9.2...v1.9.3) (2026-09-17)


### Bug Fixes

* **ci:** bump astral-sh/setup-uv from 10.0.1 to 10.1.0 ([5248a13](https://github.com/lukislp/studylife-cli/commit/5248a133ecbaf6b9a1bb237432dd94e574de174e))

## [1.9.2](https://github.com/lukislp/studylife-cli/compare/v1.9.1...v1.9.2) (2026-09-12)


### Bug Fixes

* **login:** compare the callback state as bytes so non-ASCII input cannot crash the handler ([#23](https://github.com/lukislp/studylife-cli/issues/23)) ([4b8de15](https://github.com/lukislp/studylife-cli/commit/4b8de157801ee840c7081261cdd524746792283a))

## [1.9.1](https://github.com/lukislp/studylife-cli/compare/v1.9.0...v1.9.1) (2026-09-11)


### Bug Fixes

* **ci:** read-only GITHUB_TOKEN in the Dependabot auto-merge workflow ([5d4eadf](https://github.com/lukislp/studylife-cli/commit/5d4eadf42f640133e46a8b27b2b2f724e9d8e829))

# [1.9.0](https://github.com/lukislp/studylife-cli/compare/v1.8.3...v1.9.0) (2026-09-11)


### Features

* **login:** PKCE for the StudyLife connect round trip ([de702d8](https://github.com/lukislp/studylife-cli/commit/de702d8b4ecff987cc9e6901f1a30a93435a8629))

## [1.8.3](https://github.com/lukislp/studylife-cli/compare/v1.8.2...v1.8.3) (2026-09-11)


### Bug Fixes

* **ci:** push release commits as a deploy key so the default branch can be ruleset-protected ([deb7440](https://github.com/lukislp/studylife-cli/commit/deb7440b07cd58380deda44711e0bce342968c42))

## [1.8.2](https://github.com/lukislp/studylife-cli/compare/v1.8.1...v1.8.2) (2026-09-04)


### Bug Fixes

* **ci:** bump astral-sh/setup-uv from 9.0.0 to 10.0.1 ([d9cfaab](https://github.com/lukislp/studylife-cli/commit/d9cfaabb4df8a5a0d740b68ce56177d0912e6859))

## [1.8.1](https://github.com/lukislp/studylife-cli/compare/v1.8.0...v1.8.1) (2026-09-03)


### Bug Fixes

* **ci:** add Dependabot for github-actions, uv ([88fb895](https://github.com/lukislp/studylife-cli/commit/88fb895d4fae1404e1ee42c8bfb6e84253dc4ace))

# [1.8.0](https://github.com/lukislp/studylife-cli/compare/v1.7.0...v1.8.0) (2026-08-31)


### Features

* add studylife report ([a1d87ad](https://github.com/lukislp/studylife-cli/commit/a1d87adaf842550febd15c6164ade0456f62c221))

# [1.7.0](https://github.com/lukislp/studylife-cli/compare/v1.6.0...v1.7.0) (2026-08-31)


### Features

* add studylife export ([43bc7f6](https://github.com/lukislp/studylife-cli/commit/43bc7f6a8238122c84f6223c2ae497d7fbb912ac))

# [1.6.0](https://github.com/lukislp/studylife-cli/compare/v1.5.0...v1.6.0) (2026-08-31)


### Bug Fixes

* write readable UTF-8 in --json output, not \uXXXX escapes ([8360eb9](https://github.com/lukislp/studylife-cli/commit/8360eb91018dda2a5e424c00ffc49ed715e088da))


### Features

* add studylife goals due ([73e47ab](https://github.com/lukislp/studylife-cli/commit/73e47abeb46fe55a6c188f830450d36956d21058))

# [1.5.0](https://github.com/lukislp/studylife-cli/compare/v1.4.0...v1.5.0) (2026-08-31)


### Features

* add studylife tui - a live terminal dashboard ([1d6164b](https://github.com/lukislp/studylife-cli/commit/1d6164b566bc9af078637c18c95f2cf5c76ec1dc))

# [1.4.0](https://github.com/lukislp/studylife-cli/compare/v1.3.0...v1.4.0) (2026-08-30)


### Features

* add whoami command ([ddf3aeb](https://github.com/lukislp/studylife-cli/commit/ddf3aeb783b44065c4334e22159e2d03b90c4e32))

# [1.3.0](https://github.com/lukislp/studylife-cli/compare/v1.2.0...v1.3.0) (2026-08-30)


### Features

* publish to PyPI on release via trusted publishing ([63b9a0a](https://github.com/lukislp/studylife-cli/commit/63b9a0a77067317491655e76cd5741c3a9b9cd22))

# [1.2.0](https://github.com/lukislp/studylife-cli/compare/v1.1.1...v1.2.0) (2026-08-29)


### Features

* add verb-first command aliases, trim default table columns ([1c0971e](https://github.com/lukislp/studylife-cli/commit/1c0971ea3ba05f85f0ce49e438c87e7201339dd9))

## [1.1.1](https://github.com/lukislp/studylife-cli/compare/v1.1.0...v1.1.1) (2026-08-29)


### Bug Fixes

* make --json work after the subcommand, not just before it ([b5fdc1b](https://github.com/lukislp/studylife-cli/commit/b5fdc1b7fb143dcad907585a66c363ddaa6e1550))

# [1.1.0](https://github.com/lukislp/studylife-cli/compare/v1.0.0...v1.1.0) (2026-08-29)


### Features

* sync package version to git tags, print JSON on mutations ([9a1a8ff](https://github.com/lukislp/studylife-cli/commit/9a1a8ff8aeb610e8de693a9f71441df96198c677))

# 1.0.0 (2026-08-29)


### Features

* initial studylife-cli scaffold ([68fccad](https://github.com/lukislp/studylife-cli/commit/68fccad778ce292f6d8ddba51fa3ebe7b33e83c2))
