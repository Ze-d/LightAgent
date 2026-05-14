# Agent Runtime Eval Report

| Suite | Cases | Passed | Pass Rate | Key Metrics |
|------|------:|------:|----------:|-------------|
| tool_calling | 20 | 20 | 100.0% | tool_selection_accuracy=1.000, argument_accuracy=1.000, schema_valid_rate=1.000, tool_success_rate=1.000, tool_result_contains_rate=1.000, answer_contains_rate=1.000, avg_latency_ms=0.907 |
| tool_calling_zoo | 24 | 24 | 100.0% | tool_selection_accuracy=1.000, argument_accuracy=1.000, schema_valid_rate=1.000, tool_success_rate=1.000, tool_result_contains_rate=1.000, answer_contains_rate=1.000, avg_latency_ms=0.604 |
| tool_retrieval | 19 | 19 | 100.0% | recall_at_k=1.000, schema_token_reduction_rate=0.949, irrelevant_exposure_rate=0.000, avg_selected_tool_count=2.684, min_selected_tool_count=1, max_selected_tool_count=7, namespace_cap_pass_rate=1.000 |
| checkpoint_recovery | 3 | 3 | 100.0% | recovery_success_rate=1.000, expected_outcome_rate=1.000, duplicate_tool_execution_count=0, non_idempotent_protection_rate=1.000, checkpoint_phase_correct_rate=1.000, avg_resume_latency_ms=0.317 |

## Case Results

### tool_calling

| Case | Status | Metrics |
|------|--------|---------|
| tool_calculator_multiply | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=2.521 |
| tool_calculator_parentheses | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.468 |
| tool_current_time_tokyo | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=5.874 |
| tool_current_time_new_york | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=1.202 |
| tool_convert_units_length | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.438 |
| tool_convert_units_temperature | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.392 |
| tool_analyze_text_lines | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.401 |
| tool_analyze_text_empty | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.385 |
| tool_weather_beijing | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.373 |
| tool_weather_tokyo | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.363 |
| tool_search_knowledge_toolregistry | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.393 |
| tool_search_knowledge_runner | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.371 |
| tool_memory_write_project | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.781 |
| tool_memory_write_user | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.743 |
| tool_memory_append_session | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.864 |
| tool_memory_read_session | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.511 |
| tool_memory_read_all | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.677 |
| tool_memory_search_without_vector | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.441 |
| tool_memory_stats | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.551 |
| tool_memory_consolidate_without_vector | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.385 |

### tool_calling_zoo

| Case | Status | Metrics |
|------|--------|---------|
| zoo_extract_keywords | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.515 |
| zoo_regex_extract_codes | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.425 |
| zoo_regex_extract_group | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.411 |
| zoo_normalize_whitespace | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.361 |
| zoo_json_path_read_nested | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.382 |
| zoo_json_path_read_missing | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.652 |
| zoo_csv_summarize | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.569 |
| zoo_render_markdown_table | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.478 |
| zoo_date_diff | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=1.975 |
| zoo_add_business_days | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=1.264 |
| zoo_add_business_days_zero | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.580 |
| zoo_split_tasks | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.908 |
| zoo_prioritize_tasks | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.796 |
| zoo_validate_url_valid | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.593 |
| zoo_validate_url_invalid_scheme | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.466 |
| zoo_hash_text_sha256 | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.441 |
| zoo_hash_text_md5 | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.483 |
| zoo_hash_text_unsupported | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.534 |
| zoo_dedupe_lines_case_insensitive | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.491 |
| zoo_dedupe_lines_case_sensitive | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.395 |
| zoo_sort_items_ascending | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.404 |
| zoo_sort_items_descending | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.502 |
| zoo_template_render | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.425 |
| zoo_template_render_missing_value | PASS | tool_selected_correctly=1, arguments_correct=1, schema_valid=1, tool_success=1, tool_result_contains_expected=1, answer_contains_expected=1, latency_ms=0.454 |

### tool_retrieval

| Case | Status | Metrics |
|------|--------|---------|
| retrieve_calculator | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.971, irrelevant_exposure_rate=0.000, selected_tool_count=2, namespace_cap_pass=1 |
| retrieve_markdown_table | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.929, irrelevant_exposure_rate=0.000, selected_tool_count=3, namespace_cap_pass=1 |
| retrieve_keywords | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.973, irrelevant_exposure_rate=0.000, selected_tool_count=2, namespace_cap_pass=1 |
| retrieve_url_validation | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.990, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_hash_text | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.986, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_regex | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.970, irrelevant_exposure_rate=0.000, selected_tool_count=2, namespace_cap_pass=1 |
| retrieve_business_days | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.986, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_knowledge | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.963, irrelevant_exposure_rate=0.000, selected_tool_count=2, namespace_cap_pass=1 |
| retrieve_a2a_researcher | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.988, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_github_search | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.987, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_github_prs | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.988, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_github_create_issue | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.987, irrelevant_exposure_rate=0.000, selected_tool_count=1, namespace_cap_pass=1 |
| retrieve_knowledge_to_table | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.892, irrelevant_exposure_rate=0.000, selected_tool_count=5, namespace_cap_pass=1 |
| retrieve_keyword_pipeline | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.874, irrelevant_exposure_rate=0.000, selected_tool_count=7, namespace_cap_pass=1 |
| retrieve_memory_update_pipeline | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.821, irrelevant_exposure_rate=0.000, selected_tool_count=6, namespace_cap_pass=1 |
| retrieve_csv_json_table_pipeline | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.904, irrelevant_exposure_rate=0.000, selected_tool_count=5, namespace_cap_pass=1 |
| retrieve_url_date_hash_pipeline | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.962, irrelevant_exposure_rate=0.000, selected_tool_count=3, namespace_cap_pass=1 |
| retrieve_github_issue_report_pipeline | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.893, irrelevant_exposure_rate=0.000, selected_tool_count=4, namespace_cap_pass=1 |
| retrieve_github_triage_pipeline | PASS | recall_at_k=1.000, schema_token_reduction_rate=0.962, irrelevant_exposure_rate=0.000, selected_tool_count=3, namespace_cap_pass=1 |

### checkpoint_recovery

| Case | Status | Metrics |
|------|--------|---------|
| resume_read_only_once | PASS | resume_success=1, duplicate_tool_count=0, non_idempotent_protected=0, checkpoint_phase_correct=1, resume_latency_ms=0.496 |
| resume_idempotent_once | PASS | resume_success=1, duplicate_tool_count=0, non_idempotent_protected=0, checkpoint_phase_correct=1, resume_latency_ms=0.381 |
| blocks_running_non_idempotent | PASS | resume_success=0, duplicate_tool_count=0, non_idempotent_protected=1, checkpoint_phase_correct=1, resume_latency_ms=0.074 |
