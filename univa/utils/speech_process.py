import os
import librosa
import soundfile as sf
import numpy as np
import tempfile
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
except ModuleNotFoundError:
    from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip


def _with_volume_scaled(audio_clip, factor):
    if hasattr(audio_clip, "volumex"):
        return audio_clip.volumex(factor)
    return audio_clip.with_volume_scaled(factor)


def _with_audio(video_clip, audio_clip):
    if hasattr(video_clip, "set_audio"):
        return video_clip.set_audio(audio_clip)
    return video_clip.with_audio(audio_clip)

def calculate_rms_volume_from_file(audio_file_path):
    """
    Calculate RMS volume directly from an audio file.
    
    Args:
        audio_file_path: Path to the audio file
        
    Returns:
        float: RMS volume value
    """
    try:
        # Load audio using librosa
        y, sr = librosa.load(audio_file_path, sr=None)
        
        # Calculate RMS
        rms = np.sqrt(np.mean(y**2))
        return rms
    except Exception as e:
        print(f"Error calculating audio RMS: {e}")
        return 0.1  # Return default value

def calculate_rms_volume_safe(audio_clip):
    """
    Safely calculate RMS volume of an audio clip.
    
    Args:
        audio_clip: MoviePy AudioFileClip object
        
    Returns:
        float: RMS volume value
    """
    try:
        # Try using MoviePy's method
        audio_array = audio_clip.to_soundarray()
        
        # If stereo, convert to mono
        if len(audio_array.shape) > 1:
            audio_array = np.mean(audio_array, axis=1)
        
        # Calculate RMS
        rms = np.sqrt(np.mean(audio_array**2))
        return rms
    except Exception as e:
        print(f"MoviePy volume calculation failed, trying fallback method: {e}")
        
        # Fallback method: save as temporary file and analyze with librosa
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Write to temporary file
            audio_clip.write_audiofile(temp_path, verbose=False, logger=None)
            
            # Calculate RMS using librosa
            rms = calculate_rms_volume_from_file(temp_path)
            
            # Clean up temporary file
            os.remove(temp_path)
            
            return rms
        except Exception as e2:
            print(f"Fallback volume calculation method also failed: {e2}")
            return 0.1  # Return default value

def align_and_merge_audio(audio_path: str, video_path: str, output_path: str, 
                         volume_balance_mode: str = "auto", 
                         new_audio_volume: float = 1.0, 
                         original_audio_volume: float = 1.0) -> str:
    """
    Align the duration of an audio file to a video file's duration, then merge the new audio
    with the original video's audio track, and finally generate a new video file.
    Volume balancing functionality has been added.

    This function will:
    1. Get the target duration of the video.
    2. Use librosa to perform high-quality time-domain stretching of the audio (preserving pitch).
    3. [New Feature] Analyze volume and perform balance adjustment.
    4. Use moviepy to mix the stretched audio with the original video's audio track.
    5. Clean up temporary audio files generated during the process.

    Args:
        audio_path (str): Path to the audio file to be processed (e.g., 'speech.mp3').
        video_path (str): Path to the target video file (e.g., 'background.mp4').
        output_path (str): Path to save the output synthesized video file (e.g., 'final_video.mp4').
        volume_balance_mode (str): Volume balance mode.
            - "auto": Automatically balance the volume of both audio tracks
            - "manual": Use manually set volume ratio
            - "none": Do not adjust volume
        new_audio_volume (float): Volume multiplier for the new audio (only effective in manual mode)
        original_audio_volume (float): Volume multiplier for the original video's audio track (only effective in manual mode)

    Returns:
        str: Path to the successfully generated output video file.
        
    Raises:
        FileNotFoundError: If the input audio or video file does not exist.
        Exception: If other errors occur during processing.
    """
    # --- 1. Verify that input files exist ---
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    print("--- Starting processing ---")
    print(f"Audio input: {audio_path}")
    print(f"Video input: {video_path}")
    print(f"Volume balance mode: {volume_balance_mode}")

    temp_audio_path = None  # Initialize temporary file path variable

    try:
        # --- 2. Get the duration of audio and video ---
        print("Getting file duration...")
        audio_duration = librosa.get_duration(path=audio_path)
        
        with VideoFileClip(video_path) as video_clip:
            video_duration = video_clip.duration
        
        print(f"Original audio duration: {audio_duration:.2f} seconds")
        print(f"Target video duration: {video_duration:.2f} seconds")

        # --- 3. Perform time-domain stretching on audio ---
        stretch_rate = audio_duration / video_duration
        y, sr = librosa.load(audio_path, sr=None)
        
        print(f"Stretching audio at a rate of {stretch_rate:.4f}...")
        y_stretched = librosa.effects.time_stretch(y=y, rate=stretch_rate)
        
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir) and output_dir != '':
            os.makedirs(output_dir)
        temp_audio_path = os.path.join(output_dir, f"temp_stretched_audio_{os.path.basename(output_path)}.wav")

        print(f"Saving temporary stretched audio to: {temp_audio_path}")
        sf.write(temp_audio_path, y_stretched, sr)

        # --- 4. [Modified] Merge new audio with original video's audio track (with volume balancing) ---
        print("Merging new audio with original video's audio track...")
        # Load original video
        final_video_clip = VideoFileClip(video_path)
        # Extract original video's audio track
        original_audio = final_video_clip.audio
        
        # Load the newly stretched audio
        new_audio = AudioFileClip(temp_audio_path)

        # Create a list to hold all audio tracks to be merged
        audio_clips_to_merge = []
        
        # --- 5. [New] Volume balance processing ---
        if volume_balance_mode == "auto" and original_audio:
            print("Performing automatic volume balance analysis...")
            
            try:
                # Calculate RMS volume of both audio tracks
                # For new audio, we calculate directly from the stretched file
                new_audio_rms = calculate_rms_volume_from_file(temp_audio_path)
                
                # For original audio, use the safe method
                original_audio_rms = calculate_rms_volume_safe(original_audio)
                
                print(f"New audio RMS volume: {new_audio_rms:.6f}")
                print(f"Original audio RMS volume: {original_audio_rms:.6f}")
                
                # Avoid division by zero error
                if new_audio_rms > 0 and original_audio_rms > 0:
                    # If original audio volume is larger, reduce original audio volume
                    if original_audio_rms > new_audio_rms * 1.2:  # Add 20% tolerance
                        volume_ratio = new_audio_rms / original_audio_rms
                        original_audio = _with_volume_scaled(original_audio, volume_ratio)
                        print(f"Original audio volume adjusted, multiplier: {volume_ratio:.3f}")
                    # If new audio volume is larger, reduce new audio volume
                    elif new_audio_rms > original_audio_rms * 1.2:  # Add 20% tolerance
                        volume_ratio = original_audio_rms / new_audio_rms
                        new_audio = _with_volume_scaled(new_audio, volume_ratio)
                        print(f"New audio volume adjusted, multiplier: {volume_ratio:.3f}")
                    else:
                        print("Both audio tracks have similar volume, no adjustment needed")
                else:
                    print("Problem with volume calculation, skipping automatic adjustment")
                    
            except Exception as e:
                print(f"Automatic volume balance failed: {e}")
                print("Will skip volume adjustment and continue processing...")
                
        elif volume_balance_mode == "manual":
            print(f"Applying manual volume settings...")
            new_audio = _with_volume_scaled(new_audio, new_audio_volume)
            if original_audio:
                original_audio = _with_volume_scaled(original_audio, original_audio_volume)
            print(f"New audio volume multiplier: {new_audio_volume}")
            print(f"Original audio volume multiplier: {original_audio_volume}")
        else:
            print("No volume adjustment performed")

        # Add audio track to merge list
        audio_clips_to_merge.append(new_audio)
        if original_audio:
            print("Original video audio track detected, added to merge list.")
            audio_clips_to_merge.append(original_audio)
        else:
            print("Original video has no audio track, will only add new audio.")

        # Use CompositeAudioClip to merge all audio tracks in the list
        # These audio tracks will play simultaneously
        final_audio = CompositeAudioClip(audio_clips_to_merge)
        
        # Set this merged audio track to the video
        final_clip = _with_audio(final_video_clip, final_audio)
        
        # Write the final video file
        print(f"Exporting final video to: {output_path}")
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
        # Close all open clips in time to release resources
        final_video_clip.close()
        new_audio.close()
        if original_audio:
            original_audio.close()
        final_clip.close()

        print("--- Processing successful! ---")
        return output_path

    except Exception as e:
        print(f"Error occurred during processing: {e}")
        import traceback
        traceback.print_exc()
        raise e

    finally:
        # --- 6. Clean up temporary files ---
        if temp_audio_path and os.path.exists(temp_audio_path):
            print(f"Cleaning up temporary file: {temp_audio_path}")
            os.remove(temp_audio_path)

# ===================================================================
# ---                    CLI example entrypoint                    ---
# ===================================================================
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Align speech audio with a background video.")
    parser.add_argument("--audio", required=True, help="Path to the speech audio file.")
    parser.add_argument("--video", required=True, help="Path to the background video file.")
    parser.add_argument("--output", required=True, help="Path for the merged output video.")
    parser.add_argument("--new-audio-volume", type=float, default=0.8)
    parser.add_argument("--original-audio-volume", type=float, default=0.5)
    args = parser.parse_args()

    generated_file = align_and_merge_audio(
        audio_path=args.audio,
        video_path=args.video,
        output_path=args.output,
        volume_balance_mode="manual",
        new_audio_volume=args.new_audio_volume,
        original_audio_volume=args.original_audio_volume,
    )
    print(f"Generated file: {generated_file}")
