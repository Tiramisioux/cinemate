export function toKebabCase(value: string): string {
    return value
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
        .toLowerCase();
}

export function prefixZero(value: string): string {
    let suffix = isNaN(parseInt(value, 10)) ? '' : value[value.length - 1];
    const num = parseInt(value, 10);
    if (isNaN(num)) return value;
    return num < 10 ? `0${num}${suffix}` : `${num}${suffix}`;
}
