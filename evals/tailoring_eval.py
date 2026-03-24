from langsmith import Client
from langsmith.evaluation import evaluate

from app.tools.resume_tools import check_grounding

client = Client()


def tailor_fn(inputs: dict) -> str:
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
        lambda inputs: {"tailored_resume": tailor_fn(inputs)},
        data="resume-tailoring-dataset",
        evaluators=[no_fabrication],
        experiment_prefix="tailoring-grounding",
    )


if __name__ == "__main__":
    main()
