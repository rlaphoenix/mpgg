<p align="center">
    <a href="https://github.com/rlaphoenix/mpgg">MPGG</a>
    <br/>
    <sup><em>Streamlined MPEG-1 and MPEG-2 source loader and helper utility for VapourSynth</em></sup>
</p>

<p align="center">
    <a href="https://github.com/rlaphoenix/mpgg/actions/workflows/ci.yml">
        <img src="https://github.com/rlaphoenix/mpgg/actions/workflows/ci.yml/badge.svg" alt="Build status">
    </a>
    <a href="https://python.org">
        <img src="https://img.shields.io/badge/python-3.8%20%7C%7C%203.10-informational" alt="Python version">
    </a>
    <a href="https://vapoursynth.com">
        <img src="https://img.shields.io/badge/vapoursynth-R58%2B-informational" alt="VapourSynth version">
    </a>
    <a href="https://deepsource.io/gh/rlaphoenix/mpgg/?ref=repository-badge">
        <img src="https://deepsource.io/gh/rlaphoenix/mpgg.svg/?label=active+issues&token=9rxkTrTRXcRYIVl8HjRu2sYX" alt="DeepSource">
    </a>
</p>

## Features

- 🎥 Supports MPEG-1 and MPEG-2 Sources
- 🧠 Understands Mixed-scan Sources
- 🤖 VFR to CFR (Variable to Constant frame rate)
- 🛠️ Automatic Frame-indexing using DGIndex
- ⚙️ Zero-configuration
- 🧩 Easy installation via PIP/PyPI
- ❤️ Fully Open-Source! Pull Requests Welcome

## Installation

```shell
$ pip install mpgg
```

Voilà 🎉! You now have the `mpgg` package installed, and you can now import it from a VapourSynth script.

### Dependencies

The following is a list of software that needs to be installed manually. MPGG cannot install these automatically
on your behalf.

#### Software

- [MKVToolnix] (specifically mkvextract) for demuxing MPEG streams from MKV containers.
- [DGIndex] for automatic frame-indexing of MPEG streams.

Make sure you put them in your current working directory, in the installation directory, or put the directory path in
your `PATH` environment variable. If you do not do this then their binaries will not be able to be found.

  [MKVToolNix]: <https://mkvtoolnix.download/downloads.html>
  [DGIndex]: <https://rationalqm.us/dgmpgdec/dgmpgdec.html>

#### VapourSynth Plugins

- [d2vsource] for loading an indexed DGIndex project file.

These plugins may be installed using [vsrepo] on Windows, or from a package repository on Linux.

  [d2vsource]: <https://github.com/dwbuiten/d2vsource>
  [vsrepo]: <https://github.com/vapoursynth/vsrepo>

## Usage

The following is an example of using MPGG to get a clean CFR Fully Progressive stream from an
Animated Mixed-scan VFR DVD-Video source.

```python
import functools

from mpgg import MPGG
from havsfunc import QTGMC

# load the source with verbose information printed
mpg = MPGG(r"C:\Users\John\Videos\animated_dvd_video.mkv", verbose=True)

# recover progressive frames where possible, and show which frames were recovered
mpg.recover(verbose=True)

# deinterlace any remaining interlaced frames with QTGMC, and show which frames were deinterlaced
mpg.deinterlace(
  kernel=functools.partial(QTGMC, Preset="Very Slow", FPSDivisor=2),
  verbose=True
)

# convert VFR to CFR by duplicating frames in a pattern
mpg.ceil()

# get the final clip (you may use the clip in between actions as well)
clip = mpg.clip

# ...

clip.set_output()
```

You can also chain calls! This is the same script but chained,

```python
import functools

from mpgg import MPGG
from havsfunc import QTGMC

# load MPEG, recover progressive frames, deinterlace what's left, and finally VFR to CFR
clip = MPGG(r"C:\Users\John\Videos\animated_dvd_video.mkv", verbose=True).\
  recover(verbose=True).\
  deinterlace(kernel=functools.partial(QTGMC, Preset="Very Slow", FPSDivisor=2), verbose=True).\
  ceil().\
  clip

# ...

clip.set_output()
```

There are more methods not shown here. I recommend taking a look at the MPGG class for further
information, methods, and more.

> __Warning__ Do not copy/paste and re-use these examples. Read each method's doc-string information
> as they each have their own warnings, tips, and flaws that you need to be aware of. For example,
> recover() shouldn't be used on all MPEG sources, floor() shouldn't be used with recover(), you
> may not want to use ceil() if you want to keep encoding as VFR, and such.

## Terminology

| Term           | Meaning                                                                        |
|----------------|--------------------------------------------------------------------------------|
| CFR            | Constant frame-rate, the source uses a set frame rate on playback              |
| VFR            | Variable frame-rate, the source switches frame rate at least once on playback  |
| Scan           | The technology used to show images on screens, i.e., Interlaced or Progressive |
| Mixed-scan     | Source with both Progressive and Interlaced frames within the video data       |
| Frame-indexing | Analyzing a source to index frame/field information for frame-serving          |

## Contributors

<a href="https://github.com/rlaphoenix"><img src="https://images.weserv.nl/?url=avatars.githubusercontent.com/u/17136956?v=4&h=25&w=25&fit=cover&mask=circle&maxage=7d" alt=""/></a>

## License

© 2021-2023 rlaphoenix — [GNU General Public License, Version 3.0](LICENSE)
