from pathlib import Path
from gui_spector.verfication.agent import VerficationRunner, PROMPT_TEMPLATE_V1
from gui_spector.models import Requirements, RequirementsPriority
from gui_spector.computers.docker import DockerComputer


def acknowledge_safety_check_callback(message: str) -> bool:
    print(f"Safety check: {message}")
    return True


def main() -> None:
    # Start URL and requirement description provided in the request
    start_url = "http://192.168.178.40:8002/"
    requirement_text = (
        "The keyword and min/max price inputs are staged and do not filter "
        "while typing. Results update only when the user clicks the Search "
        "button or presses Enter (resetting to page 1), while other facet filters"
        " (categories, brands, colors, rating, stock, free shipping, on sale, sort, "
        "page size) apply immediately."
    )

    requirement = Requirements.create(
        title="Explicit Search Trigger for Text and Price",
        description=requirement_text,
        tags=["ui", "datasets", "edit"],
        acceptance_criteria=[],
        priority=RequirementsPriority.MEDIUM,
    )

    # Save run artifacts to resources/runs
    package_root = Path(__file__).resolve().parent.parent
    data_dir = package_root / "resources" / "runs"
    print(f"DATA_DIR resolved to: {data_dir}")

    with DockerComputer(display=":99") as computer:
        runner = VerficationRunner(
            computer=computer,
            acknowledge_safety_check_callback=acknowledge_safety_check_callback,
            data_dir=data_dir,
            prompt_name=PROMPT_TEMPLATE_V1,
        )
        print(f"All run data will be saved in: {runner.run_dir}")
        result = runner.run(
            requirement=requirement,
            start_url=start_url,
            print_steps=True,
            show_images=False,
            debug=False,
        )

    # Print a concise summary
    print("Result:")
    print(result)
    print("Model decision:")
    print(result.model_decision)
    if result.usage_total:
        print("Total usage:")
        print(result.usage_total)
    if result.interactions:
        print("Interactions:")
        for inter in result.interactions:
            print(inter)


if __name__ == "__main__":
    main()
