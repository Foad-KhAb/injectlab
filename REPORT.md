# Indirect Prompt Injection Against a Local Tool-Using Agent

**Author:** <your name>
**Code version:** <git commit from `results/full.jsonl`>

## Abstract

<!-- 5 sentences: the problem, what you built, the main ASR result, the main defense result, the tradeoff. Write this last. -->

## 1. Setup

<!-- Agent loop, tools (9 simulated tools for email, web and calendar), and the simulated world.
Model name and quantization, temperature 0, seed, max 15 steps. Hardware (GPU model) and Ollama version.
State that everything is simulated: no real mail, no network calls from tools, `.test` addresses only. -->

## 2. Threat model

<!-- The attacker controls content the agent reads (an email, a web page, a calendar description).
The attacker cannot change the system prompt, the user's request, or the tools.
The attacker does not see the agent's output. What counts as a successful attack. -->

## 3. Tasks and attacks

### 3.1 User tasks

<!-- Table of the 8 user tasks: what each asks, which slots it reads. How success is checked:
deterministic checks on the final world state, and the source-facts rule. -->

### 3.2 Attacker goals

<!-- Table of the 5 goals and what counts as success for each. -->

### 3.3 Templates

<!-- The 5 templates, and why `persian` copies the framing of `ignore_previous`. -->

### 3.4 Experiment size

<!-- 8 benign + 250 attacked runs per defense; number of defenses; total runs; runs excluded for errors. -->

## 4. Defenses

<!-- One paragraph each: none, delimiting, sandwich, tool_filter, detector. What each changes,
and what it assumes. tool_filter gets its tool list from the task definition: say this is a best case. -->

## 5. Metrics

<!-- Utility, utility under attack (counted whether or not the attack also succeeded), ASR.
Wilson 95% intervals. Exact McNemar test for paired comparisons, with your multiple-testing correction.
answer_mentions_attacker and what it does and does not show. -->

## 6. Results

### 6.1 Baseline, no defense

<!-- Utility, utility under attack and ASR for `none`, from "Overview" in figures/tables.md. -->

### 6.2 Which attacks work

![ASR by template and defense](figures/asr_heatmap.png)

![ASR by attacker goal](figures/asr_by_goal.png)

<!-- Which template and goal are strongest, with numbers. -->

### 6.3 Defenses and their cost

![Utility against ASR](figures/tradeoff_scatter.png)

<!-- Each defense against none, from "Each defense vs none" in figures/tables.md: ASR change,
utility change, p-value. The detector's false positive rate. -->

### 6.4 English and Persian

![English and Persian](figures/english_vs_persian.png)

<!-- From "English vs Persian" in figures/tables.md. -->

## 7. Discussion

<!-- Why do these results look the way they do? Open traces to support explanations
(`injectlab show-trace`). Which defense would you deploy, and for what kind of agent? -->

## 8. Limitations

<!-- See what limits these numbers: one model, small hand-written suite, one seed, runs that share
tasks are not independent, simulated world, string-based checks. -->

## 9. Future work

<!-- More models, adaptive attacks, more languages, a detector that keeps the clean part of an output. -->

## References

- Debenedetti et al. (2024). AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.
- Greshake et al. (2023). Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.
- Hines et al. (2024). Defending Against Indirect Prompt Injection Attacks With Spotlighting.
- Perez and Ribeiro (2022). Ignore Previous Prompt: Attack Techniques For Language Models.
- Yong et al. (2023). Low-Resource Languages Jailbreak GPT-4.
- Deng et al. (2024). Multilingual Jailbreak Challenges in Large Language Models.
