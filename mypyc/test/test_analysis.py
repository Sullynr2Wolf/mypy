"""Test runner for data-flow analysis test cases."""

from __future__ import annotations

import os.path
from typing import Set

from mypy.errors import CompileError
from mypy.test.config import test_temp_dir
from mypy.test.data import DataDrivenTestCase
from mypyc.analysis import dataflow
from mypyc.common import TOP_LEVEL_NAME
from mypyc.ir.func_ir import all_values
from mypyc.ir.ops import Value
from mypyc.ir.pprint import format_func, generate_names_for_ir
from mypyc.test.testutil import (
    ICODE_GEN_BUILTINS,
    MypycDataSuite,
    assert_test_output,
    build_ir_for_single_file,
    use_custom_builtins,
)
from mypyc.transform import exceptions

files = ["analysis.test"]


class TestAnalysis(MypycDataSuite):
    files = files
    base_path = test_temp_dir
    optional_out = True

    def run_case(self, testcase: DataDrivenTestCase) -> None:
        """Perform a data-flow analysis test case."""

        with use_custom_builtins(os.path.join(self.data_prefix, ICODE_GEN_BUILTINS), testcase):
            try:
                ir = build_ir_for_single_file(testcase.input)
            except CompileError as e:
                actual = e.messages
            else:
                actual = []
                for fn in ir:
                    if fn.name == TOP_LEVEL_NAME and not testcase.name.endswith("_toplevel"):
                        continue
                    exceptions.insert_exception_handling(fn)
                    actual.extend(format_func(fn))
                    cfg = dataflow.get_cfg(fn.blocks)
                    args: Set[Value] = set(fn.arg_regs)
                    name = testcase.name
                    if name.endswith("_MaybeDefined"):
                        # Forward, maybe
                        analysis_result = dataflow.analyze_maybe_defined_regs(fn.blocks, cfg, args)
                    elif name.endswith("_Liveness"):
                        # Backward, maybe
                        analysis_result = dataflow.analyze_live_regs(fn.blocks, cfg)
                    elif name.endswith("_MustDefined"):
                        # Forward, must
                        analysis_result = dataflow.analyze_must_defined_regs(
                            fn.blocks, cfg, args, regs=all_values(fn.arg_regs, fn.blocks)
                        )
                    elif name.endswith("_BorrowedArgument"):
                        # Forward, must
                        analysis_result = dataflow.analyze_borrowed_arguments(fn.blocks, cfg, args)
                    else:
                        assert False, "No recognized _AnalysisName suffix in test case"

                    names = generate_names_for_ir(fn.arg_regs, fn.blocks)

                    for key in sorted(
                        analysis_result.before.keys(), key=lambda x: (x[0].label, x[1])
                    ):
                        pre = ", ".join(sorted(names[reg] for reg in analysis_result.before[key]))
                        post = ", ".join(sorted(names[reg] for reg in analysis_result.after[key]))
                        actual.append(
                            "%-8s %-23s %s" % ((key[0].label, key[1]), "{%s}" % pre, "{%s}" % post)
                        )
            assert_test_output(testcase, actual, "Invalid source code output")
