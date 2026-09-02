package bootstrap

import (
	"context"
	"crypto/ed25519"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func LoadChannel(ctx context.Context, downloader *Downloader, channelURL, signatureURL string, key ed25519.PublicKey) (Channel, error) {
	payload, err := downloader.Read(ctx, channelURL, 1024*1024)
	if err != nil {
		return Channel{}, err
	}
	signature, err := downloader.Read(ctx, signatureURL, 64*1024)
	if err != nil {
		return Channel{}, err
	}
	if err := VerifyBytes(payload, signature, key); err != nil {
		return Channel{}, err
	}
	var channel Channel
	if err := decodeStrictJSON(payload, &channel); err != nil {
		return Channel{}, err
	}
	channel.Identity = sha256Bytes(payload)
	if channel.Schema != ChannelSchema || channel.Channel != "stable" || channel.Sequence == 0 {
		return Channel{}, fmt.Errorf("unsupported update channel contract")
	}
	if _, err := parseVersion(channel.MinimumBootstrap); err != nil {
		return Channel{}, err
	}
	if _, err := parseVersion(channel.Updater.Version); err != nil {
		return Channel{}, err
	}
	if comparison, err := compareVersions(channel.Updater.Version, channel.MinimumBootstrap); err != nil || comparison < 0 {
		return Channel{}, fmt.Errorf("channel updater does not satisfy its minimum bootstrap version")
	}
	if err := validateArtifact("updater", channel.Updater.Artifact); err != nil {
		return Channel{}, err
	}
	if err := validateArtifact("manifest", channel.Manifest.Artifact); err != nil {
		return Channel{}, err
	}
	if strings.TrimSpace(channel.Manifest.SignatureURL) == "" {
		return Channel{}, fmt.Errorf("manifest signature URL is empty")
	}
	published, err := time.Parse(time.RFC3339, channel.PublishedUTC)
	if err != nil || published.After(time.Now().UTC().Add(24*time.Hour)) {
		return Channel{}, fmt.Errorf("channel publication time is invalid")
	}
	return channel, nil
}

func LoadUpdateManifest(ctx context.Context, downloader *Downloader, reference ManifestReference, key ed25519.PublicKey, channel Channel) (UpdateManifest, error) {
	payload, err := downloader.Read(ctx, reference.URL, reference.Size)
	if err != nil {
		return UpdateManifest{}, err
	}
	if int64(len(payload)) != reference.Size || sha256Bytes(payload) != strings.ToLower(reference.SHA256) {
		return UpdateManifest{}, fmt.Errorf("update manifest hash or size does not match the signed channel")
	}
	signature, err := downloader.Read(ctx, reference.SignatureURL, 64*1024)
	if err != nil {
		return UpdateManifest{}, err
	}
	if err := VerifyBytes(payload, signature, key); err != nil {
		return UpdateManifest{}, err
	}
	var manifest UpdateManifest
	if err := decodeStrictJSON(payload, &manifest); err != nil {
		return UpdateManifest{}, err
	}
	manifest.Identity = sha256Bytes(payload)
	if manifest.Schema != ManifestSchema || manifest.Channel != channel.Channel || manifest.Sequence != channel.Sequence {
		return UpdateManifest{}, fmt.Errorf("update manifest does not match the signed channel")
	}
	if _, err := parseVersion(manifest.Version); err != nil {
		return UpdateManifest{}, err
	}
	if !gitCommitPattern.MatchString(manifest.Commit) {
		return UpdateManifest{}, fmt.Errorf("update manifest commit is invalid")
	}
	published, err := time.Parse(time.RFC3339, manifest.PublishedUTC)
	if err != nil || published.After(time.Now().UTC().Add(24*time.Hour)) {
		return UpdateManifest{}, fmt.Errorf("update manifest publication time is invalid")
	}
	if len(manifest.Components) == 0 || len(manifest.Components) > 16 {
		return UpdateManifest{}, fmt.Errorf("update manifest contains %d components", len(manifest.Components))
	}
	componentNames := map[string]bool{}
	componentStageNames := map[string]bool{}
	for _, component := range manifest.Components {
		name := strings.TrimSpace(component.Name)
		if name == "" || name != component.Name || len(name) > 64 {
			return UpdateManifest{}, fmt.Errorf("update manifest contains an invalid component name")
		}
		key := strings.ToLower(name)
		stageKey := safeName(name)
		if componentNames[key] || componentStageNames[stageKey] {
			return UpdateManifest{}, fmt.Errorf("update manifest contains duplicate or colliding component names")
		}
		componentNames[key] = true
		componentStageNames[stageKey] = true
	}
	return manifest, nil
}

func ValidatePublishedContract(channel Channel, manifest UpdateManifest) error {
	if channel.Schema != ChannelSchema || channel.Channel != "stable" || channel.Sequence == 0 {
		return fmt.Errorf("unsupported update channel contract")
	}
	if err := ValidateReleaseVersion(channel.MinimumBootstrap); err != nil {
		return err
	}
	if err := ValidateReleaseVersion(channel.Updater.Version); err != nil {
		return err
	}
	if comparison, err := compareVersions(channel.Updater.Version, channel.MinimumBootstrap); err != nil || comparison < 0 {
		return fmt.Errorf("channel updater does not satisfy its minimum bootstrap version")
	}
	if err := validateArtifact("updater", channel.Updater.Artifact); err != nil {
		return err
	}
	if err := validateArtifact("manifest", channel.Manifest.Artifact); err != nil {
		return err
	}
	if strings.TrimSpace(channel.Manifest.SignatureURL) == "" {
		return fmt.Errorf("manifest signature URL is empty")
	}
	channelPublished, err := time.Parse(time.RFC3339, channel.PublishedUTC)
	if err != nil || channelPublished.After(time.Now().UTC().Add(24*time.Hour)) {
		return fmt.Errorf("channel publication time is invalid")
	}
	if manifest.Schema != ManifestSchema || manifest.Channel != channel.Channel || manifest.Sequence != channel.Sequence {
		return fmt.Errorf("update manifest does not match the signed channel")
	}
	if err := ValidateReleaseVersion(manifest.Version); err != nil {
		return err
	}
	if !gitCommitPattern.MatchString(manifest.Commit) {
		return fmt.Errorf("update manifest commit is invalid")
	}
	manifestPublished, err := time.Parse(time.RFC3339, manifest.PublishedUTC)
	if err != nil || manifestPublished.After(time.Now().UTC().Add(24*time.Hour)) || !manifestPublished.Equal(channelPublished) {
		return fmt.Errorf("update manifest publication time is invalid or differs from the channel")
	}
	if manifest.Relaunch != "" && manifest.Relaunch != "KFPS.exe" {
		return fmt.Errorf("unsupported relaunch target %q", manifest.Relaunch)
	}
	if len(manifest.Components) == 0 || len(manifest.Components) > 16 {
		return fmt.Errorf("update manifest contains %d components", len(manifest.Components))
	}
	componentNames := map[string]bool{}
	destinations := map[string]string{}
	for _, component := range manifest.Components {
		name := strings.TrimSpace(component.Name)
		if name == "" || name != component.Name || len(name) > 64 || componentNames[strings.ToLower(name)] {
			return fmt.Errorf("update manifest contains an invalid or duplicate component name")
		}
		componentNames[strings.ToLower(name)] = true
		if component.Target != "app-root" && component.Target != "install-root" {
			return fmt.Errorf("unsupported target %q", component.Target)
		}
		if err := validateArtifact("component "+component.Name, component.Archive); err != nil {
			return err
		}
		records, err := validateFileRecords(component.Files)
		if err != nil {
			return fmt.Errorf("component %s: %w", component.Name, err)
		}
		claim := func(path, action string) error {
			key := component.Target + ":" + pathKey(path)
			if previous, exists := destinations[key]; exists {
				return fmt.Errorf("published destination collision at %s between %s and %s", path, previous, action)
			}
			destinations[key] = action
			return nil
		}
		for _, record := range records {
			if err := validateComponentPath(component, record.Path); err != nil {
				return err
			}
			if err := claim(record.Path, component.Name+" install"); err != nil {
				return err
			}
		}
		exactSeen := map[string]bool{}
		for _, exactRoot := range component.ExactRoots {
			clean, err := cleanRelativePath(exactRoot)
			if err != nil {
				return err
			}
			if exactSeen[pathKey(clean)] || component.Name != "python-runtime" || pathKey(clean) != "python" {
				return fmt.Errorf("unsupported or duplicate exact root %q", exactRoot)
			}
			exactSeen[pathKey(clean)] = true
		}
		retiredSeen := map[string]bool{}
		for _, retired := range component.RetiredFiles {
			clean, err := cleanRelativePath(retired)
			if err != nil {
				return err
			}
			if retiredSeen[pathKey(clean)] {
				return fmt.Errorf("duplicate retired path %s", clean)
			}
			retiredSeen[pathKey(clean)] = true
			if err := validateComponentPath(component, clean); err != nil {
				return err
			}
			if err := claim(clean, component.Name+" removal"); err != nil {
				return err
			}
		}
	}
	return nil
}

func PrepareComponentUpdate(ctx context.Context, downloader *Downloader, manifest UpdateManifest, stagingRoot string, layout Layout, logger *Logger) (PreparedUpdate, error) {
	if err := preflightComponentDestinations(manifest, layout); err != nil {
		return PreparedUpdate{}, err
	}
	prepared := PreparedUpdate{
		Version: manifest.Version, Commit: manifest.Commit, Sequence: manifest.Sequence,
		ManifestSHA256: manifest.Identity, Relaunch: manifest.Relaunch,
	}
	seenDestinations := map[string]bool{}
	for _, component := range manifest.Components {
		if strings.TrimSpace(component.Name) == "" {
			return PreparedUpdate{}, fmt.Errorf("component name is empty")
		}
		if err := validateArtifact("component "+component.Name, component.Archive); err != nil {
			return PreparedUpdate{}, err
		}
		root, err := layout.TargetRoot(component.Target)
		if err != nil {
			return PreparedUpdate{}, err
		}
		records, err := validateFileRecords(component.Files)
		if err != nil {
			return PreparedUpdate{}, fmt.Errorf("component %s: %w", component.Name, err)
		}
		componentChanges := []Change{}
		for _, record := range records {
			if err := validateComponentPath(component, record.Path); err != nil {
				return PreparedUpdate{}, err
			}
			destination, err := joinContained(root, record.Path)
			if err != nil {
				return PreparedUpdate{}, err
			}
			key := pathKey(destination)
			if seenDestinations[key] {
				return PreparedUpdate{}, fmt.Errorf("multiple components manage %s", destination)
			}
			seenDestinations[key] = true
			prepared.FilesChecked++
			needsRepair, err := fileNeedsRepair(destination, record)
			if err != nil {
				return PreparedUpdate{}, err
			}
			if needsRepair {
				componentChanges = append(componentChanges, Change{Kind: ReplaceFile, Relative: record.Path, Destination: destination, Expected: record})
			}
		}
		removalSeen := map[string]bool{}
		exactRemovals, err := collectExactRootRemovals(root, component, records, removalSeen)
		if err != nil {
			return PreparedUpdate{}, err
		}
		componentChanges = append(componentChanges, exactRemovals...)
		for _, removal := range exactRemovals {
			key := pathKey(removal.Destination)
			if seenDestinations[key] {
				return PreparedUpdate{}, fmt.Errorf("multiple component operations manage %s", removal.Destination)
			}
			seenDestinations[key] = true
		}
		for _, retired := range component.RetiredFiles {
			cleanRetired, err := cleanRelativePath(retired)
			if err != nil {
				return PreparedUpdate{}, err
			}
			if err := validateComponentPath(component, cleanRetired); err != nil {
				return PreparedUpdate{}, err
			}
			if _, managed := records[pathKey(cleanRetired)]; managed {
				return PreparedUpdate{}, fmt.Errorf("component %s both installs and retires %s", component.Name, cleanRetired)
			}
			destination, err := joinContained(root, cleanRetired)
			if err != nil {
				return PreparedUpdate{}, err
			}
			key := pathKey(destination)
			if seenDestinations[key] {
				return PreparedUpdate{}, fmt.Errorf("multiple component operations manage %s", destination)
			}
			seenDestinations[key] = true
			if removalSeen[key] {
				return PreparedUpdate{}, fmt.Errorf("component %s repeats retired path %s", component.Name, cleanRetired)
			}
			removalSeen[key] = true
			info, statErr := os.Lstat(destination)
			if os.IsNotExist(statErr) {
				continue
			}
			if statErr != nil {
				return PreparedUpdate{}, statErr
			}
			if !info.Mode().IsRegular() {
				return PreparedUpdate{}, fmt.Errorf("retired path requires manual remediation because it is not a regular file: %s", destination)
			}
			componentChanges = append(componentChanges, Change{Kind: RemoveFile, Relative: cleanRetired, Destination: destination})
		}
		needsArchive := false
		for _, change := range componentChanges {
			if change.Kind == ReplaceFile {
				needsArchive = true
				break
			}
		}
		if needsArchive {
			componentStage := filepath.Join(stagingRoot, "components", safeName(component.Name))
			archivePath := filepath.Join(stagingRoot, "downloads", safeName(component.Name)+".zip")
			logger.Printf("Downloading component %s.", component.Name)
			if err := downloader.DownloadArtifact(ctx, component.Archive, archivePath); err != nil {
				return PreparedUpdate{}, err
			}
			inventory, err := openZipInventory(archivePath)
			if err != nil {
				return PreparedUpdate{}, err
			}
			if len(inventory.files) != len(records) {
				inventory.Close()
				return PreparedUpdate{}, fmt.Errorf("component %s archive inventory does not match its manifest", component.Name)
			}
			for key, record := range records {
				entry := inventory.files[key]
				if entry == nil || int64(entry.UncompressedSize64) != record.Size {
					inventory.Close()
					return PreparedUpdate{}, fmt.Errorf("component %s archive is missing %s", component.Name, record.Path)
				}
			}
			for index := range componentChanges {
				if componentChanges[index].Kind != ReplaceFile {
					continue
				}
				staged, err := joinContained(componentStage, componentChanges[index].Expected.Path)
				if err != nil {
					inventory.Close()
					return PreparedUpdate{}, err
				}
				if err := inventory.extract(componentChanges[index].Expected.Path, staged, componentChanges[index].Expected); err != nil {
					inventory.Close()
					return PreparedUpdate{}, err
				}
				componentChanges[index].Staged = staged
			}
			inventory.Close()
		}
		prepared.Changes = append(prepared.Changes, componentChanges...)
	}
	sortChanges(prepared.Changes, layout.InstallRoot)
	logger.Printf("Signed component inventory checked %d files and planned %d operation(s).", prepared.FilesChecked, len(prepared.Changes))
	return prepared, nil
}

func preflightComponentDestinations(manifest UpdateManifest, layout Layout) error {
	seen := map[string]string{}
	claim := func(destination, owner string) error {
		key := pathKey(destination)
		if previous, exists := seen[key]; exists {
			return fmt.Errorf("component operation collision at %s between %s and %s", destination, previous, owner)
		}
		seen[key] = owner
		return nil
	}
	for _, component := range manifest.Components {
		if err := validateArtifact("component "+component.Name, component.Archive); err != nil {
			return err
		}
		root, err := layout.TargetRoot(component.Target)
		if err != nil {
			return err
		}
		records, err := validateFileRecords(component.Files)
		if err != nil {
			return fmt.Errorf("component %s: %w", component.Name, err)
		}
		for _, record := range records {
			if err := validateComponentPath(component, record.Path); err != nil {
				return err
			}
			destination, err := joinContained(root, record.Path)
			if err != nil {
				return err
			}
			if err := claim(destination, component.Name+" install"); err != nil {
				return err
			}
		}
		exactRemovals, err := collectExactRootRemovals(root, component, records, map[string]bool{})
		if err != nil {
			return err
		}
		for _, removal := range exactRemovals {
			if err := claim(removal.Destination, component.Name+" exact-root removal"); err != nil {
				return err
			}
		}
		retiredSeen := map[string]bool{}
		for _, retired := range component.RetiredFiles {
			clean, err := cleanRelativePath(retired)
			if err != nil {
				return err
			}
			if err := validateComponentPath(component, clean); err != nil {
				return err
			}
			if retiredSeen[pathKey(clean)] {
				return fmt.Errorf("component %s repeats retired path %s", component.Name, clean)
			}
			retiredSeen[pathKey(clean)] = true
			destination, err := joinContained(root, clean)
			if err != nil {
				return err
			}
			if err := claim(destination, component.Name+" retired-file removal"); err != nil {
				return err
			}
		}
	}
	return nil
}

func safeName(value string) string {
	var result strings.Builder
	for _, character := range strings.ToLower(value) {
		if (character >= 'a' && character <= 'z') || (character >= '0' && character <= '9') || character == '-' || character == '_' {
			result.WriteRune(character)
		} else {
			result.WriteByte('-')
		}
	}
	if result.Len() == 0 {
		return "component"
	}
	return result.String()
}

func VerifyPreparedUpdate(prepared PreparedUpdate) error {
	for _, change := range prepared.Changes {
		switch change.Kind {
		case ReplaceFile:
			needsRepair, err := fileNeedsRepair(change.Destination, change.Expected)
			if err != nil {
				return err
			}
			if needsRepair {
				return fmt.Errorf("updated file did not verify: %s", change.Destination)
			}
		case RemoveFile:
			if _, err := os.Stat(change.Destination); !os.IsNotExist(err) {
				return fmt.Errorf("retired file still exists: %s", change.Destination)
			}
		}
	}
	return nil
}
