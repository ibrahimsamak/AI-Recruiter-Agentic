# AI-Recruiter-Agentic · LangSmith grounding eval
# evals/tailoring_eval.py
"""LangSmith grounding eval: does the tailored resume fabricate anything?

Run with a `resume-tailoring-dataset` present in LangSmith:
    python -m evals.tailoring_eval
"""
from langsmith import Client
from langsmith.evaluation import evaluate

from app.tools.resume_tools import check_grounding

client = Client()


def tailor_fn(inputs: dict) -> str:
    """Produce a tailored resume for the eval example.

    Replace with the real tailoring callable (e.g. invoke the tailoring_worker
    subagent or the orchestrator). Stubbed to echo the source so the pipeline
    is runnable end-to-end.
    """
    return inputs["source_resume"]


def no_fabrication(run, example) -> dict:
    result = check_grounding.invoke(
        {
            "source_resume": example.inputs["source_resume"],
            "tailored_resume": run.outputs["tailored_resume"],
        }
    )
    return {"key": "no_fabrication", "score": 1.0 if result["grounded"] else 0.0}


def main():
    evaluate(
        lambda inputs: {"tailored_resume": tailor_fn(inputs)},  # your tailoring callable
        data="resume-tailoring-dataset",  # dataset in LangSmith
        evaluators=[no_fabrication],
        experiment_prefix="tailoring-grounding",
    )


if __name__ == "__main__":
    main()
