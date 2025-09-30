from gui_spector.computers import LocalPlaywrightBrowser, DockerComputer, BrowserbaseBrowser

computers_config = {
    "local-playwright": LocalPlaywrightBrowser,
    "docker": DockerComputer,
    "browserbase": BrowserbaseBrowser,
}
