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
        #expect(local.media.preprocessingHints["external_url_policy"] == "local_media_allowed")
        #expect(local.media.preprocessingHints["external_url_source_kind"] == "local")
        #expect(local.media.preprocessingHints["external_url_scheme"] == "path")
        #expect(remote.imageUri == "https://example.com/remote-image.png")
        #expect(remote.media.sourceKind == .mediaSourceUri)
        #expect(remote.media.preprocessingHints["detail"] == "high")
        #expect(remote.media.preprocessingHints["external_url_policy"] == "external_https_public_only")
        #expect(remote.media.preprocessingHints["external_url_source_kind"] == "remote")
        #expect(remote.media.preprocessingHints["external_url_scheme"] == "https")
        #expect(remote.media.preprocessingHints["external_url_host"] == "example.com")
    }

    @Test("external media URL admission allows local and public HTTPS while refusing unsafe remote hosts")
    func externalMediaURLAdmissionCoversLocalPublicAndUnsafeRemoteCases() throws {
        let localPath = try ExternalMediaURLAdmission.validate("/tmp/local-image.png", mediaKind: "image")
        let fileURL = try ExternalMediaURLAdmission.validate("file:///tmp/local-image.png", mediaKind: "image")
        let publicURL = try ExternalMediaURLAdmission.validate(
            " HTTPS://Example.com/remote-image.png ",
            mediaKind: "image"
        )

        #expect(localPath.policy == "local_media_allowed")
        #expect(localPath.sourceKind == "local")
        #expect(localPath.scheme == "path")
        #expect(fileURL.scheme == "file")
        #expect(publicURL.policy == "external_https_public_only")
        #expect(publicURL.sourceKind == "remote")
        #expect(publicURL.scheme == "https")
        #expect(publicURL.host == "example.com")
        #expect(publicURL.reason == "accepted_https_public_host_without_fetch")

        let refusals: [(String, ExternalMediaURLAdmissionError)] = [
            ("", .malformedURL("image")),
            ("http://[::1", .malformedURL("image")),
            ("http://example.com/image.png", .unsupportedScheme("http")),
            ("https:///image.png", .missingHost),
            ("https://localhost/image.png", .privateHost("localhost")),
            ("https://service.localhost/image.png", .privateHost("service.localhost")),
            ("https://127.0.0.1/image.png", .privateHost("127.0.0.1")),
            ("https://10.0.0.1/image.png", .privateHost("10.0.0.1")),
            ("https://169.254.1.1/image.png", .privateHost("169.254.1.1")),
            ("https://172.16.0.1/image.png", .privateHost("172.16.0.1")),
            ("https://192.168.0.1/image.png", .privateHost("192.168.0.1")),
            ("https://[::1]/image.png", .privateHost("[::1]")),
            ("https://[fe80::1]/image.png", .privateHost("[fe80::1]")),
            ("https://[fc00::1]/image.png", .privateHost("[fc00::1]")),
            ("https://[fd00::1]/image.png", .privateHost("[fd00::1]")),
        ]

        for (rawURL, expectedError) in refusals {
            do {
                _ = try ExternalMediaURLAdmission.validate(rawURL, mediaKind: "image")
                Issue.record("Expected \(rawURL) to be refused.")
            } catch let error as ExternalMediaURLAdmissionError {
                #expect(error == expectedError)
                #expect(error.operatorMessage == expectedError.operatorMessage)
                #expect(error.refusalReason == expectedError.refusalReason)
            } catch {
                Issue.record("Unexpected error: \(error)")
            }
        }
    }

    @Test("multimodal request normalizer rejects private external image URLs")
    func privateExternalImageURLsAreRejectedWithTypedOperatorErrors() {
        let normalizer = MultimodalRequestNormalizer()
        let privateImage = OpenAIMultimodalContentPart(
            type: .inputImage,
            inputImage: OpenAIMultimodalImageReference(
                url: "https://127.0.0.1/private.png",
                mimeType: "image/png"
            )
        )

        do {
            _ = try normalizer.normalize(privateImage)
            Issue.record("Expected private image URL to fail.")
        } catch let error as MultimodalRequestNormalizationError {
            #expect(error == .externalMediaURLBlocked("External media URL host is not allowed: 127.0.0.1."))
            #expect(error.operatorMessage == "External media URL host is not allowed: 127.0.0.1.")
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("multimodal request normalizer preserves multi-image ordering")
    func multiImageOrderingIsPreserved() throws {
        let decoder = JSONDecoder()
        let messages = try decoder.decode(
            [OpenAIMultimodalMessage].self,
            from: Data(
                """
                [
                  {
                    "role": "user",
                    "content": [
                      { "type": "text", "text": "Compare the images." },
                      {
                        "type": "input_image",
                        "input_image": {
                          "url": "/tmp/first-image.png",
                          "filename": "first-image.png"
                        }
                      },
                      {
                        "type": "image_url",
                        "image_url": {
                          "url": "https://example.com/second-image.png",
                          "filename": "second-image.png"
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
        #expect(normalized[0].parts[0].text == "Compare the images.")
        #expect(normalized[0].parts[1].imageUri == "/tmp/first-image.png")
        #expect(normalized[0].parts[2].imageUri == "https://example.com/second-image.png")
        #expect(normalized[0].parts[1].media.filename == "first-image.png")
        #expect(normalized[0].parts[2].media.filename == "second-image.png")
    }

    @Test("multimodal request normalizer emits stable shared media part summaries")
    func sharedMediaPartSummaryRecordsOrderingSourcesAndDigests() throws {
        let decoder = JSONDecoder()
        let messages = try decoder.decode(
            [OpenAIMultimodalMessage].self,
            from: Data(
                """
                [
                  {
                    "role": "system",
                    "content": [
                      { "type": "text", "text": "Use the media carefully." }
                    ]
                  },
                  {
                    "role": "user",
                    "content": [
                      { "type": "text", "text": "Compare these inputs." },
                      {
                        "type": "input_image",
                        "input_image": {
                          "data": "aW1hZ2U=",
                          "mime_type": "image/png",
                          "format": "png",
                          "filename": "inline.png"
                        }
                      },
                      {
                        "type": "input_audio",
                        "input_audio": {
                          "data": "YXVkaW8=",
                          "format": "wav",
                          "filename": "clip.wav"
                        }
                      },
                      {
                        "type": "input_video",
                        "input_video": {
                          "data": "dmlkZW8=",
                          "format": "mp4",
                          "filename": "clip.mp4"
                        }
                      },
                      {
                        "type": "image_url",
                        "image_url": {
                          "url": "https://example.com/reference.png",
                          "format": "png",
                          "filename": "reference.png"
                        }
                      },
                      {
                        "type": "input_video",
                        "input_video": {
                          "url": "/tmp/local-demo.mov",
                          "format": "mov",
                          "filename": "local-demo.mov"
                        }
                      }
                    ]
                  }
                ]
                """.utf8
            )
        )

        let normalizer = MultimodalRequestNormalizer()
        let firstSummary = try normalizer.mediaPartsSummary(for: messages)
        let secondSummary = try normalizer.mediaPartsSummary(for: messages)

        #expect(firstSummary.parts == secondSummary.parts)
        #expect(firstSummary.parts.map(\.mediaKind) == ["image", "audio", "video", "image", "video"])
        #expect(firstSummary.parts.map(\.turnIndex) == [1, 1, 1, 1, 1])
        #expect(firstSummary.parts.map(\.partIndex) == [1, 2, 3, 4, 5])
        #expect(firstSummary.parts.map(\.sourceKind) == ["inline_bytes", "inline_bytes", "inline_bytes", "remote", "local"])

        let image = firstSummary.parts[0]
        #expect(image.source == "inline_bytes")
        #expect(image.byteLength == 5)
        #expect(image.filename == "inline.png")
        #expect(image.format == "png")
        #expect(image.stableDigest?.count == 64)

        let audio = firstSummary.parts[1]
        #expect(audio.byteLength == 5)
        #expect(audio.filename == "clip.wav")
        #expect(audio.format == "wav")
        #expect(audio.stableDigest == firstSummary.parts[1].stableDigest)
        #expect(audio.stableDigest != image.stableDigest)

        let video = firstSummary.parts[2]
        #expect(video.byteLength == 5)
        #expect(video.filename == "clip.mp4")
        #expect(video.format == "mp4")
        #expect(video.stableDigest != image.stableDigest)

        let remoteImage = firstSummary.parts[3]
        #expect(remoteImage.source == "https://example.com/reference.png")
        #expect(remoteImage.byteLength == nil)
        #expect(remoteImage.filename == "reference.png")
        #expect(remoteImage.format == "png")
        #expect(remoteImage.stableDigest?.count == 64)

        let localVideo = firstSummary.parts[4]
        #expect(localVideo.source == "/tmp/local-demo.mov")
        #expect(localVideo.byteLength == nil)
        #expect(localVideo.filename == "local-demo.mov")
        #expect(localVideo.format == "mov")
        #expect(localVideo.stableDigest?.count == 64)
        #expect(localVideo.stableDigest != remoteImage.stableDigest)
    }

    @Test("multimodal request normalizer accepts image-only payloads")
    func imageOnlyPayloadsNormalizeWithoutSyntheticText() throws {
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
                        "type": "input_image",
                        "input_image": {
                          "data": "aGVsbG8=",
                          "mime_type": "image/png",
                          "filename": "image-only.png"
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
        #expect(normalized[0].parts.count == 1)
        #expect(normalized[0].parts[0].imageBytes == Data("hello".utf8))
        #expect(normalized[0].parts[0].media.sourceKind == .mediaSourceInlineBytes)
        #expect(normalized[0].parts[0].media.filename == "image-only.png")
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

    @Test("multimodal message contracts decode and normalize video uri and inline payloads")
    func messageContractsDecodeAndNormalizeVideoPayloads() throws {
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()

        let uriPart = try decoder.decode(
            OpenAIMultimodalContentPart.self,
            from: Data(
                """
                {
                  "type": "input_video",
                  "input_video": {
                    "url": "https://example.com/demo.mov",
                    "mime_type": "video/quicktime",
                    "duration_ms": 12000,
                    "frame_budget": 12,
                    "start_ms": 500,
                    "end_ms": 3500
                  }
                }
                """.utf8
            )
        )
        let inlinePart = try decoder.decode(
            OpenAIMultimodalContentPart.self,
            from: Data(
                """
                {
                  "type": "input_video",
                  "video_base64": "dmlkZW8=",
                  "mime_type": "video/mp4",
                  "filename": "inline.mp4",
                  "duration_ms": 4000,
                  "frame_budget": 8,
                  "start_ms": 0,
                  "end_ms": 2400
                }
                """.utf8
            )
        )

        let normalizer = MultimodalRequestNormalizer()
        let normalizedURI = try normalizer.normalize(uriPart)
        let normalizedInline = try normalizer.normalize(inlinePart)

        #expect(normalizedURI.videoUri == "https://example.com/demo.mov")
        #expect(normalizedURI.media.mediaType == .video)
        #expect(normalizedURI.media.sourceKind == .mediaSourceUri)
        #expect(normalizedURI.media.mimeType == "video/quicktime")
        #expect(normalizedURI.media.format == "mov")
        #expect(normalizedURI.media.filename == "demo.mov")
        #expect(normalizedURI.media.durationMs == 12_000)
        #expect(normalizedURI.media.frameBudget == 12)
        #expect(normalizedURI.media.startMs == 500)
        #expect(normalizedURI.media.endMs == 3_500)
        #expect(normalizedURI.media.preprocessingHints["external_url_policy"] == "external_https_public_only")
        #expect(normalizedURI.media.preprocessingHints["external_url_host"] == "example.com")

        #expect(normalizedInline.videoBytes == Data("video".utf8))
        #expect(normalizedInline.media.mediaType == .video)
        #expect(normalizedInline.media.sourceKind == .mediaSourceInlineBytes)
        #expect(normalizedInline.media.format == "mp4")
        #expect(normalizedInline.media.filename == "inline.mp4")
        #expect(normalizedInline.media.byteLength == 5)
        #expect(normalizedInline.media.durationMs == 4_000)
        #expect(normalizedInline.media.frameBudget == 8)
        #expect(normalizedInline.media.endMs == 2_400)

        let encoded = try encoder.encode([uriPart, inlinePart])
        let roundTripped = try decoder.decode([OpenAIMultimodalContentPart].self, from: encoded)

        #expect(roundTripped.count == 2)
        #expect(roundTripped[0].inputVideo?.url == "https://example.com/demo.mov")
        #expect(roundTripped[1].inputVideo?.data == "dmlkZW8=")
    }

    @Test("multimodal request normalizer rejects invalid video payloads with typed operator errors")
    func invalidVideoPayloadsAreRejectedWithTypedOperatorErrors() {
        let normalizer = MultimodalRequestNormalizer()

        let unsupportedScheme = OpenAIMultimodalContentPart(
            type: .inputVideo,
            inputVideo: OpenAIMultimodalVideoReference(
                url: "ftp://example.com/demo.mov",
                format: "mov"
            )
        )
        let unsupportedFormat = OpenAIMultimodalContentPart(
            type: .inputVideo,
            inputVideo: OpenAIMultimodalVideoReference(
                url: "https://example.com/demo.avi",
                format: "avi"
            )
        )
        let invalidFrameBudget = OpenAIMultimodalContentPart(
            type: .inputVideo,
            inputVideo: OpenAIMultimodalVideoReference(
                data: "dmlkZW8=",
                format: "mp4",
                frameBudget: 129
            )
        )
        let invalidBounds = OpenAIMultimodalContentPart(
            type: .inputVideo,
            inputVideo: OpenAIMultimodalVideoReference(
                data: "dmlkZW8=",
                format: "mp4",
                durationMs: 1_000,
                startMs: 600,
                endMs: 1_200
            )
        )

        do {
            _ = try normalizer.normalize(unsupportedScheme)
            Issue.record("Expected unsupported video URI scheme to fail.")
        } catch let error as MultimodalRequestNormalizationError {
            #expect(error == .unsupportedURIScheme("video", "ftp"))
            #expect(error.operatorMessage == "Unsupported video URI scheme: ftp.")
        } catch {
            Issue.record("Unexpected error: \(error)")
        }

        do {
            _ = try normalizer.normalize(unsupportedFormat)
            Issue.record("Expected unsupported video format to fail.")
        } catch let error as MultimodalRequestNormalizationError {
            #expect(error == .unsupportedMediaFormat("video", "avi"))
            #expect(error.operatorMessage == "Unsupported video format: avi.")
        } catch {
            Issue.record("Unexpected error: \(error)")
        }

        do {
            _ = try normalizer.normalize(invalidFrameBudget)
            Issue.record("Expected invalid frame budget to fail.")
        } catch let error as MultimodalRequestNormalizationError {
            #expect(error == .invalidPreprocessingBound("frame_budget", "must be less than or equal to 128"))
            #expect(error.operatorMessage == "frame_budget must be less than or equal to 128.")
        } catch {
            Issue.record("Unexpected error: \(error)")
        }

        do {
            _ = try normalizer.normalize(invalidBounds)
            Issue.record("Expected invalid video bounds to fail.")
        } catch let error as MultimodalRequestNormalizationError {
            #expect(error == .invalidPreprocessingBound("end_ms", "must be less than or equal to duration_ms"))
            #expect(error.operatorMessage == "end_ms must be less than or equal to duration_ms.")
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("multimodal video contracts cover filename inference missing payload decode and invalid scalar bounds")
    func videoContractsCoverInferenceDecodeAndScalarValidation() throws {
        let decoder = JSONDecoder()
        let normalizer = MultimodalRequestNormalizer()

        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_video")) {
            _ = try decoder.decode(
                OpenAIMultimodalContentPart.self,
                from: Data(
                    """
                    {
                      "type": "input_video"
                    }
                    """.utf8
                )
            )
        }

        let filenameInferred = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .inputVideo,
                inputVideo: OpenAIMultimodalVideoReference(
                    url: "/tmp/local-video.webm",
                    filename: "clip.webm"
                )
            )
        )
        #expect(filenameInferred.videoUri == "/tmp/local-video.webm")
        #expect(filenameInferred.media.format == "webm")
        #expect(filenameInferred.media.filename == "clip.webm")

        let urlInferred = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .inputVideo,
                inputVideo: OpenAIMultimodalVideoReference(
                    url: "file:///tmp/sample.m4v"
                )
            )
        )
        #expect(urlInferred.videoUri == "file:///tmp/sample.m4v")
        #expect(urlInferred.media.format == "m4v")
        #expect(urlInferred.media.filename == "sample.m4v")

        let inlineFallbackFilename = try normalizer.normalize(
            OpenAIMultimodalContentPart(
                type: .inputVideo,
                inputVideo: OpenAIMultimodalVideoReference(
                    data: "dmlkZW8=",
                    format: "mp4"
                )
            )
        )
        #expect(inlineFallbackFilename.media.filename == "inline-video")

        #expect(throws: MultimodalRequestNormalizationError.invalidBase64("video")) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(
                        data: "not-base64",
                        format: "mp4"
                    )
                )
            )
        }
        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_video")) {
            _ = try normalizer.normalize(OpenAIMultimodalContentPart(type: .inputVideo))
        }
        #expect(
            throws: MultimodalRequestNormalizationError.unsupportedMediaFormat("video", "video/x-matroska")
        ) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(
                        url: "https://example.com/demo",
                        mimeType: "video/x-matroska"
                    )
                )
            )
        }
        #expect(
            throws: MultimodalRequestNormalizationError.missingValue("input_video.format or input_video.mime_type")
        ) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(url: "https://example.com/demo")
                )
            )
        }
        #expect(
            throws: MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "duration_ms",
                "must be greater than 0"
            )
        ) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(
                        data: "dmlkZW8=",
                        format: "mp4",
                        durationMs: 0
                    )
                )
            )
        }
        #expect(
            throws: MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "start_ms",
                "must be greater than or equal to 0"
            )
        ) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(
                        data: "dmlkZW8=",
                        format: "mp4",
                        startMs: -1
                    )
                )
            )
        }
        #expect(
            throws: MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "frame_budget",
                "must be greater than 0"
            )
        ) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(
                        data: "dmlkZW8=",
                        format: "mp4",
                        frameBudget: 0
                    )
                )
            )
        }
        #expect(
            throws: MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "end_ms",
                "must be greater than or equal to start_ms"
            )
        ) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(
                        data: "dmlkZW8=",
                        format: "mp4",
                        startMs: 900,
                        endMs: 600
                    )
                )
            )
        }
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
        #expect(throws: MultimodalRequestNormalizationError.missingValue("input_video.data or input_video.url")) {
            _ = try normalizer.normalize(
                OpenAIMultimodalContentPart(
                    type: .inputVideo,
                    inputVideo: OpenAIMultimodalVideoReference(format: "mp4")
                )
            )
        }
    }
}
