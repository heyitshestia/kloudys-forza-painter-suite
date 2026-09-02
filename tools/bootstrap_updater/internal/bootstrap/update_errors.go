package bootstrap

import (
	"errors"
	"io"
)

type availabilityError struct{ cause error }

func (failure availabilityError) Error() string { return failure.cause.Error() }
func (failure availabilityError) Unwrap() error { return failure.cause }

func unavailable(cause error) error {
	if cause == nil {
		return nil
	}
	var existing availabilityError
	if errors.As(cause, &existing) {
		return cause
	}
	return availabilityError{cause: cause}
}

func isAvailabilityError(failure error) bool {
	var target availabilityError
	return errors.As(failure, &target)
}

type policyError struct{ cause error }

func (failure policyError) Error() string { return failure.cause.Error() }
func (failure policyError) Unwrap() error { return failure.cause }

func policyFailure(cause error) error {
	if cause == nil {
		return nil
	}
	return policyError{cause: cause}
}

func isPolicyError(failure error) bool {
	var target policyError
	return errors.As(failure, &target)
}

type availabilityReader struct{ reader io.Reader }

func (reader availabilityReader) Read(buffer []byte) (int, error) {
	count, err := reader.reader.Read(buffer)
	if err != nil && !errors.Is(err, io.EOF) {
		return count, unavailable(err)
	}
	return count, err
}
