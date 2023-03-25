from __future__ import annotations

import functools
import math
from collections import Counter
from pathlib import Path
from typing import Optional

import vapoursynth as vs
from more_itertools import split_at
from pyd2v import D2V
from pymediainfo import MediaInfo
from vapoursynth import core

from mpgg.utilities import get_aspect_ratio, get_par, get_standard, group_numbers, list_select_every


class MPGG:
    def __init__(self, file: str, verbose: bool = False):
        """
        Index MPEG-1 or MPEG-2 file with DGIndex and load with Derek dwbuiten's d2v source loader.

        Automatic indexing will take place if no D2V for the file was found. You may
        explicitly load a D2V file if the MPEG file it indexed is somewhere else.

        Specific settings are used when indexing to have full compatibility will all
        kinds of scan configurations. Pre-existing D2V files should be deleted before
        being used with MPGG, unless it was indexed by MPGG. This is because they may
        have been indexed with unsupported settings.

        Warning: The integrity of the `flags` data relative to the internal `clip` is
            crucial for the accuracy of any function called from hence forth. If you
            modify the internal clip, please make sure to update the `flags` data
            appropriately. Modifying the internal clip is not recommended.

        Parameters:
            file: The video file to load. It may be an MKV, VOB, MPG/MPEG, or a D2V.
            verbose: Print useful information about the source, and it's scan type.
        """
        if not hasattr(core, "d2v"):
            raise EnvironmentError(
                "Required plugin 'd2vsource' is not installed. "
                "See https://github.com/dwbuiten/d2vsource"
            )

        # TODO: Somehow add a check that the D2V was indexed by pyd2v
        self.d2v = D2V.load(Path(file))

        self.file = self.d2v.path
        self.flags = self._get_flags(self.d2v)
        self.pulldown, self.pulldown_str = self._get_pulldown(self.flags)
        self.total_frames = len(self.flags)
        self.p_frames = sum(f["progressive_frame"] for f in self.flags)
        self.i_frames = self.total_frames - self.p_frames

        # A DVD-spec MPEG stream is considered VFR if there's interlaced and progressive frames,
        # otherwise it would only ever be NTSC (30000/1001i) or PAL (25i), therefore constant.
        self.vfr = any(f["progressive_frame"] and f["rff"] and f["tff"] for f in self.flags) and any(
            not f["progressive_frame"] for f in self.flags)

        # Do not apply RFF (Repeat First Field) as this would be the flags for Software Pulldown.
        # We do not want to cause further interlacing. Instead, we will handle this later using
        # either ceil() or floor(). Or, the user can leave it alone to retain VFR.
        self.clip = core.d2v.Source(self.file, rff=False)

        # We must copy the flags to each frame/field of the clip, or we cannot make important
        # decisions after frame rate adjustments as the mapping to `flags` would be lost.
        self.clip = self._stamp_frames(self.clip, self.flags)

        # Override the _ColorRange value set by core.d2v.Source with one obtained from
        # the container/stream if available, or fallback and assume limited/TV.
        # This makes YUVRGB_Scale setting redundant to reduce possibilities of mistakes.
        video_track = next(iter(MediaInfo.parse(self.d2v.videos[0]).video_tracks), None)
        if video_track and getattr(video_track, "color_range", None):
            color_range = {"Full": 0, "Limited": 1}[video_track.color_range]
        else:
            color_range = 1  # assume limited/TV as MPEGs most likely are
        self.clip = core.std.SetFrameProp(self.clip, "_ColorRange", color_range)

        self.standard = get_standard(self.clip.fps.numerator / self.clip.fps.denominator)
        self.dar = self.d2v.settings["Aspect_Ratio"]
        if isinstance(self.dar, list):
            self.dar = self.dar[0]
        self.sar = get_aspect_ratio(self.clip.width, self.clip.height)
        self.par = get_par(self.clip.width, self.clip.height, *[int(x) for x in self.dar.split(":")])

        if verbose:
            progressive_p = (self.p_frames / self.total_frames) * 100
            self.clip = core.text.Text(
                self.clip,
                text=" " + (" \n ".join([
                    f"Progressive: {progressive_p:05.2f}% ({self.p_frames})" + (
                        f" w/ Pulldown {self.pulldown_str} (Cycle: {self.pulldown})" if self.pulldown else
                        " - No Pulldown"
                    ),
                    f"Interlaced:  {100 - progressive_p:05.2f}% ({self.total_frames - self.p_frames})",
                    f"VFR? {self.vfr}  DAR: {self.dar}  SAR: {self.sar}  PAR: {self.par}",
                    self.standard
                ])) + " ",
                alignment=1,
                scale=1
            )

        if not self.vfr and not self.i_frames:
            # MPEG is fully progressive (via Pulldown flags), so core.d2v.Source gives it
            # an FPS of e.g., 30000/1001, when it should be e.g., 24000/1001.
            self.floor()
            self.pulldown = None

    def recover(self, verbose=False, **kwargs):
        """
        Recovers progressive frames from an interlaced clip using VIVTC VFM.

        Do not provide `order` (TFF/BFF) argument manually unless you need to override the auto-detected
        order, or it could not be auto-detected.

        For possible arguments, see the VIVTC docs here:
        <https://github.com/vapoursynth/vivtc/blob/master/docs/vivtc.rst>

        Tips: - Only use this on sources where the majority of combed frames are recoverable (e.g. Animation),
                otherwise you are risking jerkiness and making your script slower for likely no gain.
              - Use this before *any* frame rate, length, or visual adjustments, including before deinterlacing.
              - This may add irregular duplicate frames, You should use VDecimate afterwards.
              - Do NOT use `floor()` if you use this method, it will not be safe.
        """
        if not isinstance(self.clip, vs.VideoNode):
            raise TypeError("This is not a clip")

        matched_tff = core.vivtc.VFM(self.clip, order=1, **kwargs)
        matched_bff = core.vivtc.VFM(self.clip, order=0, **kwargs)

        def _m(n: int, f: vs.VideoFrame, c: vs.VideoNode, tff: vs.VideoNode, bff: vs.VideoNode):
            # frame marked as progressive, skip matching
            if f.props["PVSFlagProgressiveFrame"] or f.props.get("_Combed") == 0:
                if c.format and tff.format and c.format.id != tff.format.id:
                    c = core.resize.Point(c, format=tff.format.id)
                return core.text.Text(c, "Progressive", alignment=3) if verbose else c
            # interlaced frame, match (if _FieldBased is > 0)
            rc = {0: c, 1: bff, 2: tff}[f.props["_FieldBased"]]  # type: ignore
            return core.text.Text(
                rc,
                "Matched (%s)" % {0: "Recovered", 1: "Combed <!>"}[rc.get_frame(n).props["_Combed"]],
                alignment=3
            ) if verbose else rc

        self.clip = core.std.FrameEval(
            matched_tff,
            functools.partial(
                _m,
                c=self.clip,
                tff=matched_tff,
                bff=matched_bff
            ),
            prop_src=self.clip
        )
        return self

    def deinterlace(self, kernel: functools.partial, verbose: bool = False) -> MPGG:
        """
        Deinterlace clip only on frames that are marked as interlaced.

        Frames that are recovered with :meth:`recover` will be skipped. However, if
        VFM detected combing in the frame, it will be deinterlaced.

        The kernel should be a function that accepts a `clip` VideoNode in the first
        positional argument. It must also accept a `TFF`/`tff` keyword argument.
        You can pass kernel settings via `functools.partial`. For example::

            kernel = functools.partial(QTGMC, FPSDivisor=2, Preset="VeryFast")

        If the kernel you want to use does not accept a `TFF`/`tff` keyword argument,
        you can manually proxy it to another argument with a lambda function, e.g.,::

            def foo(clip, field: int, preset: str):
                # pseudo-kernel using `field` to indicate tff/bff
                # ...

            kernel = functools.partial(lambda clip, tff: foo(clip, field=tff, preset="Fast"))

        You should not manually specify TFF/field order as the field order is automatically
        determined. In fact, it actually supports clips which switch field order on the fly!

        Parameters:
            kernel: A function to pass the clip through when it needs deinterlacing.
            verbose: Print useful information about the deinterlacing result.
        """
        if not isinstance(self.clip, vs.VideoNode):
            raise TypeError(f"Expected clip to be a {vs.VideoNode}, not {self.clip!r}")
        if not callable(kernel):
            raise TypeError(f"Expected kernel to be a function, not {kernel!r}")
        if len(kernel.args) > 1:
            # causes conflicts with the clip positional argument
            raise ValueError("Invalid kernel arguments, no positional arguments are allowed")

        deinterlaced_tff = kernel(self.clip, TFF=True)
        deinterlaced_bff = kernel(self.clip, TFF=False)

        fps_factor = deinterlaced_tff.fps.numerator / deinterlaced_tff.fps.denominator
        fps_factor = fps_factor / (self.clip.fps.numerator / self.clip.fps.denominator)
        if fps_factor not in (1.0, 2.0):
            # TODO: Add support for more, we might already support mod2, e.g., 2/4/8/16/e.t.c
            raise ValueError(
                f"The kernel returned an unsupported frame-rate ({deinterlaced_tff.fps}). " +
                "Only single-rate and double-rate deinterlacing is currently supported."
            )

        def _d(n: int, f: vs.VideoFrame, c: vs.VideoNode, tff: vs.VideoNode, bff: vs.VideoNode, ff: int):
            # Frame marked as progressive by DGIndex or VFM, skip deinterlacing
            if f.props["PVSFlagProgressiveFrame"] or f.props.get("_Combed") == 0:
                # duplicate if not a single-rate fps output
                rc = core.std.Interleave([c] * ff) if ff > 1 else c
                if rc.format and tff.format and rc.format.id != tff.format.id:
                    rc = core.resize.Spline16(rc, format=tff.format.id)
                return core.text.Text(
                    rc,
                    # space it to keep recover()'s verbose logs visible
                    "Progressive" + ["", "\n"]["_Combed" in f.props],
                    alignment=3
                ) if verbose else rc
            # Frame otherwise assumed to be interlaced or progressively encoded interlacing.
            # It won't deinterlace progressive frames here unless recover() was run and detected
            # that the frame was interlaced by detecting visual combing artifacts.
            # Do note that deinterlacing progressively encoded interlaced frames don't always look
            # the best, but not much can really be done in those cases.
            order = f.props["_FieldBased"]
            if f.props.get("_Combed", 0) != 0:
                order = 2  # TODO: Don't assume TFF
            rc = {0: c, 1: bff, 2: tff}[order]  # type: ignore
            field_order = {0: "Progressive <!>", 1: "BFF", 2: "TFF"}[order]  # type: ignore
            return core.text.Text(
                rc,
                ("Deinterlaced (%s)" % field_order) + ["", "\n"]["_Combed" in f.props],
                alignment=3
            ) if verbose else rc

        self.clip = core.std.FrameEval(
            deinterlaced_tff,
            functools.partial(
                _d,
                c=self.clip,
                tff=deinterlaced_tff,
                bff=deinterlaced_bff,
                ff=int(fps_factor)  # TODO: floor/ceil instead?
            ),
            prop_src=self.clip
        )

        return self

    def ceil(self) -> MPGG:
        """
        VFR to CFR by duplicating progressive frames with the RFF flag.

        This does the same operation as honoring pulldown/RFF, but without
        interlacing the progressive frames, resulting in a mixed-scan stream
        and no further spatial loss.
        """
        if not self.vfr:
            return self

        pf = [i for i, f in enumerate(self.flags) if f["progressive_frame"] and f["rff"] and f["tff"]]

        self.clip = core.std.DuplicateFrames(self.clip, pf)

        def disable_rff(n: int, f: vs.VideoFrame) -> vs.VideoFrame:
            f = f.copy()
            f.props["PVSFlagRff"] = 0
            return f

        self.clip = core.std.ModifyFrame(self.clip, self.clip, disable_rff)
        self.flags = [
            flag
            for i, f in enumerate(self.flags)
            for flag in [dict(f, rff=False)] * (2 if i in pf else 1)
        ]

        self.vfr = False
        return self

    def floor(self, cycle: int = None, offsets: list[int] = None) -> MPGG:
        """
        VFR to CFR by decimating interlaced sections to match progressive sections.

        Warning: Do not use this function if it causes the duration to change. Do not use
            this function if you used recover() or VFM. If duplicate frames are in an
            irregular pattern then the constant cycle and pattern decimation method of
            this function will result in an incorrect duration with audio and subtitle
            desyncing. This should only be used on a clean source where any software or
            hard pulldown is in a consistent pattern. If the duration is changing, use
            VDecimate instead.

        Parameters:
            cycle: Defaults to the pulldown cycle.
            offsets: Defaults to keeping the last frame of each cycle.
        """
        cycle = cycle or self.pulldown
        if cycle:
            offsets = offsets
            if offsets is None:
                offsets = list(range(cycle - 1))
            if not offsets or len(offsets) >= cycle:
                raise ValueError("Invalid offsets, cannot be empty or have >= items of cycle")

            wanted_fps_num = self.clip.fps.numerator - (self.clip.fps.numerator / cycle)
            progressive_sections = group_numbers([n for n, f in enumerate(self.flags) if f["progressive_frame"]])
            interlaced_sections = group_numbers([n for n, f in enumerate(self.flags) if not f["progressive_frame"]])

            self.clip = core.std.Splice([x for _, x in sorted(
                [
                    (
                        x[0],  # first frame # of the section, used for sorting when splicing
                        core.std.AssumeFPS(
                            self.clip[x[0]:x[-1] + 1],
                            fpsnum=wanted_fps_num,
                            fpsden=self.clip.fps.denominator
                        )
                    ) for x in progressive_sections
                ] + [
                    (
                        x[0],
                        core.std.SelectEvery(
                            self.clip[x[0]:x[-1] + 1],
                            cycle,
                            offsets
                        )
                    ) for x in interlaced_sections
                ],
                key=lambda section: int(section[0])
            )])
            interlaced_frames = [
                n
                for s in interlaced_sections
                for n in list_select_every(s, cycle, offsets, inverse=True)
            ]
            self.flags = [f for i, f in enumerate(self.flags) if i not in interlaced_frames]
            self.vfr = False
        return self

    @staticmethod
    def _stamp_frames(clip: vs.VideoNode, flags: list[dict]) -> vs.VideoNode:
        """Stamp frames with prop data that may be needed."""

        def _set_flag_props(n, f, c, fl):
            for key, value in fl[n].items():
                if isinstance(value, bool):
                    value = 1 if value else 0
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                c = core.std.SetFrameProp(c, **{
                    ("intval" if isinstance(value, int) else "data"): value
                }, prop="PVSFlag%s" % key.title().replace("_", ""))
            return c[n]

        vob_indexes = [v for _, v in {f["vob"]: n for n, f in enumerate(flags)}.items()]
        vob_indexes = [
            "%s-%s" % ((0 if n == 0 else (vob_indexes[n - 1] + 1)), i)
            for n, i in enumerate(vob_indexes)
        ]
        clip = core.std.SetFrameProp(clip, prop="PVSVobIdIndexes", data=" ".join(vob_indexes))

        return core.std.FrameEval(
            clip,
            functools.partial(
                _set_flag_props,
                c=clip,
                fl=flags
            ),
            prop_src=clip
        )

    @staticmethod
    def _get_flags(d2v: D2V) -> list[dict]:
        """Get Flag Data from D2V object."""
        return [
            dict(**flag, vob=d["vob"], cell=d["cell"])
            for d in d2v.data
            for flag in d["flags"]
        ]

    @staticmethod
    def _get_pulldown(flags: list[dict]) -> tuple[int, Optional[str]]:
        """
        Get most commonly used Pulldown cycle and syntax string.
        Returns tuple (pulldown, cycle), or (0, None) if Pulldown is not used.
        """
        # TODO: Find a safe way to get cycle, i.e. not resort to most common digit.
        #       Previously I would do this code on all progressive rff indexes, but when it entered and
        #       exited interlaced sections the right index vs left index were very far apart, messing up
        #       the accuracy of the cycles. I cannot find out why my test source (Family Guy S01E01 USA
        #       NTSC) is still having random different numbers in each (now progressive only) sections.
        sections = [
            section
            for split in split_at(
                [dict(x, i=n) for n, x in enumerate(flags)],
                lambda flag: not flag["progressive_frame"]
            )
            for section in [[flag["i"] for flag in split if flag["rff"] and flag["tff"]]]
            if section and len(section) > 1
        ]
        if not sections:
            return 0, None

        cycle = Counter([
            Counter([
                (right - left)
                for left, right in zip(indexes[::2], indexes[1::2])
            ]).most_common(1)[0][0]
            for indexes in sections
        ]).most_common(1)[0][0] + 1

        pulldown = ["2"] * math.floor(cycle / 2)
        if cycle % 2:
            pulldown.pop()
            pulldown.append("3")

        return cycle, ":".join(pulldown)


__ALL__ = (MPGG,)
