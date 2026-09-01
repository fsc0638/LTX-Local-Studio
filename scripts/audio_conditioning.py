"""Experimental distilled audio conditioning, using upstream A2Vid's frozen
audio-latent mechanism with the installed distilled schedule (not a Dev claim).
Reference: Lightricks/LTX-2, ltx_pipelines/a2vid_two_stage.py.
"""
import logging
import os


class FrozenAudioStage:
    def __init__(self, stage, latent):
        self.stage, self.latent = stage, latent

    def __getattr__(self, name):
        return getattr(self.stage, name)

    def __call__(self, **kwargs):
        from ltx_pipelines.utils.types import ModalitySpec
        kwargs["audio"] = ModalitySpec(context=kwargs["audio"].context, frozen=True,
                                     noise_scale=0.0, initial_latent=self.latent)
        logging.info("Studio: frozen source-audio conditioning applied to diffusion stage")
        return self.stage(**kwargs)


def install(distilled):
    from ltx_core.model.audio_vae import encode_audio
    from ltx_core.types import AudioLatentShape
    from ltx_pipelines.utils.blocks import AudioConditioner
    from ltx_pipelines.utils.media_io import decode_audio_from_file

    original = distilled.DistilledPipeline

    class AudioConditionedDistilled(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.source_audio_conditioner = AudioConditioner(kwargs["model_paths"].audio_vae(), self.dtype, self.device)

        def __call__(self, *args, **kwargs):
            duration = kwargs["num_frames"] / kwargs["frame_rate"]
            decoded = decode_audio_from_file(os.environ["LTX_AUDIO_REFERENCE"], self.device, 0.0, duration)
            if decoded is None:
                raise ValueError("Could not decode conditioning audio")
            latent = self.source_audio_conditioner(lambda encoder: encode_audio(decoded, encoder, None))
            shape = AudioLatentShape.from_duration(batch=1, duration=duration, channels=8, mel_bins=16)
            if latent.shape[2] < shape.frames:
                raise ValueError("Conditioning audio latent is too short")
            latent = latent[:, :, :shape.frames]
            previous = self.stage
            self.stage = FrozenAudioStage(previous, latent)
            try:
                return super().__call__(*args, **kwargs)
            finally:
                self.stage = previous

    distilled.DistilledPipeline = AudioConditionedDistilled
