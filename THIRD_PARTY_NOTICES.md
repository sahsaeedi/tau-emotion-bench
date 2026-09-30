# Third-party notices

This repository is licensed under the Apache License 2.0 (see [LICENSE](LICENSE)).
It includes code and data from the projects below: τ²-bench, τ-bench and τ-trait
under the MIT License, and ToolOrchestra under the Apache License 2.0. Their
copyright and permission notices are reproduced here, as those licenses require.

## τ²-bench

- Source: https://github.com/sierra-research/tau2-bench
- Used for: the evaluation framework in `src/tau_emotion/` (agent, user simulator,
  orchestrator, environment, evaluator, runner, CLI) and the tests and their
  fixtures, with modifications. τ²-bench's `Tool` class
  (`src/tau_emotion/environment/tool.py`) is itself adapted from
  appl (`appl/core/tool.py`, linked in that file).

```
MIT License

Copyright (c) 2025 Sierra Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## τ-bench

- Source: https://github.com/sierra-research/tau-bench
- Used for: TRACER's airline and retail environments
  (`tracer/tracer/envs/{airline,retail}/`: tools, rules, policy), the environment
  base class, user simulator and `Tool` base class (`tracer/tracer/envs/base.py`,
  `user.py`, `tool.py`), and the agent classes (`tracer/tracer/agents/`) and types
  that the task generator builds on, with modifications.

```
MIT License

Copyright (c) 2024 Sierra

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## τ-trait

- Source: https://github.com/collinear-ai/tau-trait
- Used for: TRACER's telecom and telehealth environments
  (`tracer/tracer/envs/{telecom,telehealth}/`: tools, rules, policy, data), with
  modifications. τ-trait is a fork of τ-bench, under the same license.

```
MIT License

Copyright (c) 2024 Sierra

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## ToolOrchestra

- Source: https://github.com/NVlabs/ToolOrchestra
- Used for: the bank, basketball, movie, restaurant, school and travel domains
  (the ToolScale domains in `data/tau2/domains/` and
  `evaluation/tau2-bench/tau2/domains/`): their tools, policies and databases, in
  TRACER's environments (`tracer/tracer/envs/{bank,basketball,movie,restaurant,school,travel}/`)
  and the benchmark (`src/tau_emotion/domains/` and `data/tau_emotion/domains/`),
  with modifications.

```
Copyright 2025 Hanrong Ye

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
