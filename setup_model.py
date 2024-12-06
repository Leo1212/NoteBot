import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

def setup_whisper_model(model_id, device_setting, cache_dir="cache"):
    # Set device and dtype
    if(device_setting == 'cpu'):
        device = 'cpu'
    elif device_setting == 'cuda':
        device = 'cuda:0'
    elif device_setting == 'auto':
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    else:
        device = device_setting
    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    # Load processor first
    processor = AutoProcessor.from_pretrained(model_id)

    # Load the model with proper configuration
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
        use_safetensors=True,
        cache_dir=cache_dir,
    )
    model.config.pad_token_id = processor.tokenizer.pad_token_id
    model.to(device)

    # Create ASR pipeline with modified settings
    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
        model_kwargs={
            "use_flash_attention_2": False,
            "pad_token_id": processor.tokenizer.pad_token_id,
        },
        generate_kwargs={
            "task": "transcribe",
            # "language": "en",
        }
    )
    return pipe