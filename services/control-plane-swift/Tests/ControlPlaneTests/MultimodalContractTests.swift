import Foundation
import Testing

@testable import MelixControlPlaneCore

struct MultimodalContractTests {
    @Test("multimodal message contracts decode image-uri and audio-inline payload shapes")
    func messageContractsDecodeImageAndAudioPayloads() throws {
        let decoder = JSONDecoder()
        let messages = try decoder.decode(
            [OpenAIMultimodalMessage].self,
            from: Data(
                """
                [
                  {
                    "role": "user",
                    "content": [
                      {
                        "type": "text",
                        "text": "Describe this image and audio clip."
                      },
                      {
                        "type": "image_url",
                        "image_url": {
                          "url": "file:///tmp/example.png",
                          "detail": "high",
                          "mime_type": "image/png"
                        }
                      },
                      {
                        "type": "input_audio",
                        "input_audio": {
                          "data": "aGVsbG8=",
                          "format": "wav",
                          "mime_type": "audio/wav"
                        }
                      }
                    ]
                  }
                ]
                """.utf8
            )
        )

        let normalized = try MultimodalRequestNormalizer().normalize(messages)

        #expect(normalized.count == 1)
        #expect(normalized[0].parts.count == 3)
        #expect(normalized[0].parts[0].text == "Describe this image and audio clip.")
        #expect(normalized[0].parts[1].imageUri == "file:///tmp/example.png")
        #expect(normalized[0].parts[1].media.mediaType == .image)
        #expect(normalized[0].parts[1].media.sourceKind == .mediaSourceUri)
        #expect(normalized[0].parts[1].media.mimeType == "image/png")
        #expect(normalized[0].parts[1].media.preprocessingHints["detail"] == "high")
        #expect(normalized[0].parts[2].audioBytes == Data("hello".utf8))
        #expect(normalized[0].parts[2].media.mediaType == .audio)
        #expect(normalized[0].parts[2].media.sourceKind == .mediaSourceInlineBytes)
        #expect(normalized[0].parts[2].media.format == "wav")
        #expect(normalized[0].parts[2].media.byteLength == 5)
    }

    @Test("multimodal message contracts normalize inline-image payloads with metadata")
    func inlineImagePayloadsNormalizeWithMetadata() throws {
        let decoder = JSONDecoder()
        let message = try decoder.decode(
            OpenAIMultimodalMessage.self,
            from: Data(
                """
                {
                  "role": "user",
                  "content": [
                    {
                      "type": "input_image",
                      "input_image": {
                        "data": "aGVsbG8=",
                        "mime_type": "image/png",
                        "format": "png",
                        "filename": "fixture.png"
                      },
                      "detail": "low"
                    }
                  ]
                }
                """.utf8
            )
        )

        let normalized = try MultimodalRequestNormalizer().normalize(message)
        let part = try #require(normalized.parts.first)

        #expect(part.imageBytes == Data("hello".utf8))
        #expect(part.media.mediaType == .image)
        #expect(part.media.sourceKind == .mediaSourceInlineBytes)
        #expect(part.media.mimeType == "image/png")
        #expect(part.media.format == "png")
        #expect(part.media.filename == "fixture.png")
        #expect(part.media.preprocessingHints["detail"] == "low")
        #expect(part.media.byteLength == 5)
    }

    @Test("multimodal request normalizer accepts input-image urls for local and remote ingress")
    func inputImageURLsNormalizeToImageURIs() throws {
        let normalizer = MultimodalRequestNormalizer()

        let local = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .inputImage,
                inputImage: OpenAIMultimodalImageReference(
                    url: "/tmp/local-image.png",
                    mimeType: "image/png",
                    filename: "local-image.png"
                )
            )
        )
        let remote = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .inputImage,
                inputImage: OpenAIMultimodalImageReference(
                    url: "https://example.com/remote-image.png",
                    detail: "high",
                    mimeType: "image/png"
                )
            )
        )

        #expect(local.imageUri == "/tmp/local-image.png")
        #expect(local.media.sourceKind == .mediaSourceUri)
        #expect(local.media.filename == "local-image.png")
        #expect(remote.imageUri == "https://example.com/remote-image.png")
        #expect(remote.media.sourceKind == .mediaSourceUri)
        #expect(remote.media.preprocessingHints["detail"] == "high")
    }

    @Test("multimodal request normalizer rejects invalid inline base64 payloads")
    func invalidInlineBase64PayloadsAreRejected() {
        let part = OpenAIMultimodalContentPart(
            type: .inputAudio,
            inputAudio: OpenAIMultimodalAudioReference(data: "not-base64", format: "wav")
        )

        #expect(throws: MultimodalRequestNormalizationError.invalidBase64("audio")) {
            _ = try MultimodalRequestNormalizer().normalize(part)
        }
    }

    @Test("multimodal message contracts support flat convenience payloads and encoded round-trips")
    func messageContractsSupportFlatConveniencePayloadsAndRoundTrips() throws {
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()

        let imagePart = try decoder.decode(
            OpenAIMultimodalContentPart.self,
            from: Data(
                """
                {
                  "type": "input_image",
                  "image_base64": "aGVsbG8=",
                  "mime_type": "image/jpeg",
                  "format": "jpeg",
                  "filename": "fixture.jpg",
                  "detail": "auto"
                }
                """.utf8
            )
        )
        let audioPart = try decoder.decode(
            OpenAIMultimodalContentPart.self,
            from: Data(
                """
                {
                  "type": "input_audio",
                  "audio_base64": "d29ybGQ=",
                  "mime_type": "audio/mpeg",
                  "format": "mp3",
                  "filename": "clip.mp3"
                }
                """.utf8
            )
        )
        let imageURLPart = OpenAIMultimodalContentPart(
            type: .imageURL,
            imageURL: OpenAIMultimodalImageReference(url: "file:///tmp/example.png", detail: "high")
        )
        let textPart = OpenAIMultimodalContentPart(type: .text, text: "hello")

        let normalizer = MultimodalRequestNormalizer()
        let normalizedImage = try normalizer.normalize(imagePart)
        let normalizedAudio = try normalizer.normalize(audioPart)
        let normalizedImageURL = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .imageURL,
                imageURL: OpenAIMultimodalImageReference(data: "aGVsbG8=", mimeType: "image/png")
            )
        )
        let normalizedAudioURL = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .inputAudio,
                inputAudio: OpenAIMultimodalAudioReference(url: "file:///tmp/example.wav", format: "wav")
            )
        )

        #expect(normalizedImage.imageBytes == Data("hello".utf8))
        #expect(normalizedImage.media.filename == "fixture.jpg")
        #expect(normalizedImage.media.preprocessingHints["detail"] == "auto")
        #expect(normalizedAudio.audioBytes == Data("world".utf8))
        #expect(normalizedAudio.media.filename == "clip.mp3")
        #expect(normalizedImageURL.imageBytes == Data("hello".utf8))
        #expect(normalizedImageURL.media.sourceKind == .mediaSourceInlineBytes)
        #expect(normalizedAudioURL.audioUri == "file:///tmp/example.wav")
        #expect(normalizedAudioURL.media.sourceKind == .mediaSourceUri)

        let encoded = try encoder.encode([textPart, imageURLPart, imagePart, audioPart])
        let roundTripped = try decoder.decode([OpenAIMultimodalContentPart].self, from: encoded)

        #expect(roundTripped.count == 4)
        #expect(roundTripped[0].text == "hello")
        #expect(roundTripped[1].imageURL?.url == "file:///tmp/example.png")
        #expect(roundTripped[2].inputImage?.data == "aGVsbG8=")
        #expect(roundTripped[3].inputAudio?.data == "d29ybGQ=")
    }

    @Test("multimodal request normalizer rejects missing content values")
    func missingContentValuesAreRejected() {
        let normalizer = MultimodalRequestNormalizer()

        #expect(throws: MultimodalRequestNormalizationError.missingValue("text")) {
            _ = try normalizer.normalize(OpenAIMultimodalContentPart(type: .text))
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("image_url")) {
            _ = try normalizer.normalize(OpenAIMultimodalContentPart(type: .imageURL))
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_image")) {
            _ = try normalizer.normalize(OpenAIMultimodalContentPart(type: .inputImage))
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_audio")) {
            _ = try normalizer.normalize(OpenAIMultimodalContentPart(type: .inputAudio))
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_image.url or input_image.data")) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputImage,
                    inputImage: OpenAIMultimodalImageReference()
                )
            )
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("image_url.url or image_url.data")) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .imageURL,
                    imageURL: OpenAIMultimodalImageReference()
                )
            )
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_audio.data or input_audio.url")) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputAudio,
                    inputAudio: OpenAIMultimodalAudioReference()
                )
            )
        }
    }
}
