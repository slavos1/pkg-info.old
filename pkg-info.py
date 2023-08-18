import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from stat import ST_SIZE
from subprocess import check_output
from typing import Callable, Iterable, Optional
from loguru import logger

DEFAULT_MAX_WORKERS = 10


@dataclass
class PackageInfo:
    name: str
    version: Optional[str] = ""
    desc: str = ""
    size: int = field(init=False, default=-1)
    size_human: str = field(init=False, default="")
    error: Optional[str] = ""

    def set_size(self, value):
        self.size = value
        self.size_human = f"{self.size/(2**20):.2f} MiB"

    def as_tsv(self):
        return "\t".join(
            map(str, (self.size_human, self.name, self.version, self.desc, self.error))
        )


def get_package_size(package_name: str) -> int:
    logger.info("Checking size of {!r}", package_name)
    size = 0
    for f in map(Path, check_output(["dpkg", "-L", package_name]).decode().splitlines()):
        try:
            if f.is_file() and not f.is_symlink():
                logger.trace("package_name={}, f={}", package_name, f)
                try:
                    size += f.stat()[ST_SIZE]
                except:
                    pass
        except Exception as exc:
            logger.warning("Error when accessing {}: {}", f, exc)
    return size


def update_size(
    packages: Iterable[PackageInfo], max_workers: int = DEFAULT_MAX_WORKERS
) -> Iterable[PackageInfo]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_package_size, info.name): info for info in packages}
        for future in concurrent.futures.as_completed(futures):
            info = futures[future]
            try:
                package_size: PackageInfo = future.result()
            except Exception as exc:
                info.error = exc
                logger.error("An error for {}: {}", info.name, exc)
            else:
                info.set_size(package_size)
                logger.success("Got size for {!r}: {}", info.name, info.size)
            yield info


def get_packages():
    for line in check_output(["dpkg", "-l"]).decode().splitlines():
        logger.trace(line)
        try:
            status, name, version, _, desc = line.strip().split(maxsplit=4)
        except ValueError:
            continue
        if not status == "ii":
            continue
        yield PackageInfo(name, version, desc)


def add_size_human(d):
    d.update(size_human=f"{d['size']/(2**20):.2f} MiB")
    return d


def main(is_included: Callable = lambda x: True) -> None:
    packages = filter(is_included, get_packages())
    packages = list(update_size(packages))
    total = PackageInfo("total")
    total.set_size(sum(p.size for p in packages))
    logger.info("Total is: {}", total.size_human)
    for p in packages:
        print(p.as_tsv())
    print(total.as_tsv())


if __name__ == "__main__":
    # main(lambda x: "docker" in x.name)
    main()
